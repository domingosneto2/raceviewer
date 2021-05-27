import sqlite3
import f1_2020_telemetry.packets as packets
from driver_names import driver_names

class FinalClassification:
    def __init__(self, position, num_laps, total_race_time, penalties_time):
        self.position = position
        self.num_laps = num_laps
        self.total_race_time = total_race_time
        self.penalties_time = penalties_time

    def final_time_with_penalties(self):
        return self.total_race_time + self.penalties_time

    @staticmethod
    def from_packet(packet):
        return FinalClassification(packet.position, packet.numLaps, packet.totalRaceTime, packet.penaltiesTime)


class ParticipantInfo:
    def __init__(self, driver_id, team_id, race_number, name):
        self.driver_id = driver_id
        self.team_id = team_id
        self.race_number = race_number
        self.is_active = True
        self.driver_name = name
        if self.driver_id in driver_names:
            self.driver_name = driver_names[self.driver_id]


class CarInfo:
    def __init__(self, timestamp, position, lap_number, lap_distance, total_distance, pit_status,
                 result_status, penalties):
        self.timestamp = timestamp
        self.position = position
        self.lap_number = lap_number
        self.lap_distance = lap_distance
        self.total_distance = total_distance
        self.pit_status = pit_status
        self.result_status = result_status
        self.penalties = penalties

    def __repr__(self):
        return str(vars(self))


class SafetyCarEvent:
    def __init__(self, status, timestamp):
        self.status = status
        self.timestamp = timestamp

    def __repr__(self):
        return str(vars(self))


class FastestLapInfo:
    def __init__(self, timestamp, time, driver_idx):
        self.timestamp = timestamp
        self.time = time
        self.driver_idx = driver_idx


def get_leader(packet):
    return [i for i in range(len(packet.lapData)) if packet.lapData[i].carPosition == 1][0]


def get_top_running_car(packet, num_laps):
    leader = None
    leader_position = None
    for i in range(len(packet.lapData)):
        car = packet.lapData[i]
        if car.carPosition <= 0:
            continue
        if car.currentLapNum <= num_laps and (leader is None or car.carPosition < leader_position):
            leader = i
            leader_position = car.carPosition
            if leader_position == 1:
                return leader

    if leader is None:
        return get_leader(packet)
    else:
        return leader


class LapInfo:
    def __init__(self, pkt_id, packet, prev_lap):
        leader = get_leader(packet)
        self.lap_number = max([d.currentLapNum for d in packet.lapData])
        self.driver_start_times = [None] * len(packet.lapData)
        self.leader_at_start = leader
        self.driver_start_times[leader] = 0
        self.lap_duration = None
        self.events = []
        self.safety_car_events = []
        self.start_pkt_id = pkt_id
        self.end_pkt_id = None
        if prev_lap is None:
            self.start_timestamp = 0
        else:
            self.start_timestamp = prev_lap.start_timestamp + prev_lap.lap_duration
        self.end_timestamp = self.start_timestamp

    def update_drivers_status(self, packet):
        if self.end_pkt_id is None:
            leader = get_leader(packet)
            self.lap_duration = packet.lapData[leader].currentLapTime + self.driver_start_times[leader]
            self.end_timestamp = self.start_timestamp + self.lap_duration
        for i in range(len(packet.lapData)):
            if self.driver_start_times[i] is None and packet.lapData[i].currentLapNum == self.lap_number:
                self.driver_start_times[i] = self.lap_duration

    def end_lap(self, end_pkt_id):
        self.end_pkt_id = end_pkt_id

    def add_event(self, packet):
        self.events.append(packet)

    def add_safety_car_event(self, status, timestamp):
        if len(self.safety_car_events) == 0 or self.safety_car_events[-1].status != status:
            self.safety_car_events.append(SafetyCarEvent(status, timestamp))

    def is_formation_lap(self):
        return len([e for e in self.safety_car_events if e.status == 3]) > 0

    def __repr__(self):
        return str(vars(self))


class Session:
    def __init__(self, filename, driver_filename):
        self.filename = filename
        self.conn = sqlite3.connect(filename)
        self.replay_cursor = None
        self.flashbacks = self.identify_flashbacks()
        self.delete_flashbacks()
        self.driver_names = self.load_driver_names(driver_filename)

        self.safety_car_status = None
        self.fastest_lap_info = None
        self.race_position = None
        self.chequered_flag = None
        self.active_participants = [p for p in self.get_participants_info() if p.is_active]

        self.next_packet = None

        self.laps = None
        self.cursor = None

        self.num_laps = None

    def get_record(self, query):
        cursor = self.conn.cursor()
        cursor.execute(query)
        record = cursor.fetchone()
        cursor.close()
        return record

    def get_track_length(self):
        query = "SELECT packet FROM packets WHERE packetId = 1 ORDER BY pkt_id;"
        packet_bytes, = self.get_record(query)
        packet = packets.unpack_udp_packet(packet_bytes)
        return packet.trackLength

    def get_participants_info(self):
        query = "SELECT packet FROM packets WHERE packetId = 4 ORDER BY pkt_id;"
        packet_bytes, = self.get_record(query)
        packet = packets.unpack_udp_packet(packet_bytes)
        participants = [ParticipantInfo(p.driverId, p.teamId, p.raceNumber, p.name) for p in packet.participants]
        for i in range(len(participants)):
            participants[i].is_active = i < packet.numActiveCars

        for name in self.driver_names:
            participants[i].driver_name = name

        return participants

    def get_final_classification(self):
        query = "SELECT packet FROM packets WHERE packetId = 8 ORDER BY pkt_id;"
        packet_bytes, = self.get_record(query)
        packet = packets.unpack_udp_packet(packet_bytes)
        return [FinalClassification.from_packet(p) for p in packet.classificationData]

    def get_number_of_laps(self):
        query = "SELECT packet FROM packets WHERE packetId = 1 ORDER BY pkt_id;"
        packet_bytes, = self.get_record(query)
        packet = packets.unpack_udp_packet(packet_bytes)
        return packet.totalLaps

    def identify_flashbacks(self):
        cursor = self.conn.cursor()
        query = "SELECT pkt_id, packet FROM packets WHERE packetId = 2 ORDER BY pkt_id;"
        session_packets = []
        flashbacks = []
        cursor.execute(query)
        record = cursor.fetchone()
        while record is not None:
            (pkt_id, packet_bytes) = record
            packet = packets.unpack_udp_packet(packet_bytes)
            flashback = len(session_packets) - 1
            while flashback >= 0 and self.is_flashback(session_packets[flashback], (pkt_id, packet)):
                flashback -= 1
            if flashback != len(session_packets) - 1:
                flashbacks.append((session_packets[flashback + 1][0], pkt_id))
            session_packets.append((pkt_id, packet))
            record = cursor.fetchone()
        cursor.close()
        return flashbacks

    @staticmethod
    def is_flashback(previous_record, record):
        (pkt_id, packet) = record
        (prev_pkt_id, prev_packet) = previous_record

        for i in range(len(packet.lapData)):
            ld = packet.lapData[i]
            prev_ld = prev_packet.lapData[i]
            if ld.resultStatus == 2 and prev_ld.resultStatus == 2:
                if ld.currentLapNum < prev_ld.currentLapNum or \
                        ld.currentLapNum == prev_ld.currentLapNum and ld.currentLapTime < prev_ld.currentLapTime:
                    return True
                else:
                    return False

    def delete_flashbacks(self):
        for (pkt1, pkt2) in self.flashbacks:
            cursor = self.conn.cursor()
            query = f"DELETE FROM PACKETS WHERE pkt_id >= {pkt1} AND PKT_ID < {pkt2}"
            cursor.execute(query)
        self.conn.commit()

    def get_lap_info(self):
        cursor = self.conn.cursor()
        query = "SELECT sessionTime, pkt_id, packetId, packet FROM packets WHERE packetId in (1, 2, 3) ORDER BY pkt_id;"
        cursor.execute(query)
        timestamped_packet = cursor.fetchone()
        current_lap_info = None
        lap_infos = []
        current_lap = None

        while timestamped_packet is not None:
            (timestamp, pkt_id, packetId, packet_bytes) = timestamped_packet
            packet = packets.unpack_udp_packet(packet_bytes)
            if packetId == 3 and packet.eventStringCode.decode() == "SSTA":
                # Sometimes we see two SSTA one after the other, this is trying to handle that.
                if current_lap_info and not current_lap_info.is_formation_lap():
                    current_lap_info = None
                    del lap_infos[-1]

                current_lap = 0

            if packetId == 3 and packet.eventStringCode.decode() == "SEND":
                current_lap_info.end_lap(pkt_id)
                current_lap_info = None

            if packetId == 2:
                packet_lap = max([d.currentLapNum for d in packet.lapData])
                running_cars = [d.currentLapNum for d in packet.lapData if d.resultStatus == 2]
                if len(running_cars) == 0:
                    min_running_lap = packet_lap
                else:
                    min_running_lap = min([d.currentLapNum for d in packet.lapData if d.resultStatus == 2])
                # print(f"{min_running_lap} - {packet_lap}")
                if packet_lap > current_lap:
                    if current_lap_info is not None:
                        current_lap_info.end_lap(pkt_id)
                    current_lap_info = LapInfo(pkt_id, packet, current_lap_info)
                    lap_infos.append(current_lap_info)
                    current_lap = packet_lap
                for i in range(packet_lap - min_running_lap + 1):
                    # print(f"Updating lap {-i} status")
                    lap_infos[-1 - i].update_drivers_status(packet)

            # Need this to track if the lap is a formation lap
            if packetId == 1:
                if current_lap_info is not None:
                    current_lap_info.add_safety_car_event(packet.safetyCarStatus, timestamp)

            if packetId == 3:
                if current_lap_info is not None:
                    current_lap_info.add_event(packet)

            timestamped_packet = cursor.fetchone()
        if current_lap_info is not None:
            current_lap_info.end_lap(pkt_id)
        cursor.close()

        return lap_infos

    def start_race_replay(self, skip_formation_lap):
        self.laps = self.get_lap_info()
        if self.laps[0].is_formation_lap():
            del self.laps[0]
        self.num_laps = self.get_number_of_laps()
        if skip_formation_lap:
            self.laps = [lap for lap in self.laps if not lap.is_formation_lap()]
        start_pkt_id = self.laps[0].start_pkt_id
        self.cursor = self.conn.cursor()
        query = f"SELECT sessionTime, pkt_id, packetId, packet FROM packets WHERE packetId IN (1, 2, 3) AND pkt_id > {start_pkt_id} ORDER BY pkt_id"
        self.cursor.execute(query)

        self.safety_car_status = 0
        self.fastest_lap_info = None
        self.race_position = None
        self.chequered_flag = False

        self.next_packet = self.cursor.fetchone()

    def get_current_race_position(self):
        return self.race_position

    def get_race_duration(self, race_position):
        # Car timestamps stop updating after they cross the finish line
        for car in race_position:
            if car.lap_number < self.num_laps:
                return car.timestamp

        # Looks like everybody crossed the finish line.  Best we can do is get the highest
        # timestamp available
        return max(car.timestamp for car in race_position)

    def get_current_race_duration(self):
        return self.get_race_duration(self.race_position)

    def get_race_position(self, packet):
        result = []
        leader = get_top_running_car(packet, self.num_laps)
        leader_lap = packet.lapData[leader].currentLapNum
        if leader_lap != self.laps[leader_lap - 1].lap_number:
            print(f"Blue hat, green hat: {leader_lap}")
        leader_lap_start_time = self.laps[leader_lap - 1].driver_start_times[leader]
        leader_current_lap_time = packet.lapData[leader].currentLapTime
        lap_duration = leader_lap_start_time + leader_current_lap_time
        race_duration = self.laps[leader_lap - 1].start_timestamp + lap_duration

        # print(f"{time.time()} {current_lap} {leader} {leader_lap_start_time} {leader_current_lap_time} {lap_duration}")

        for i in range(len(packet.lapData)):
            lap_data = packet.lapData[i]
            result.append(CarInfo(race_duration, lap_data.carPosition, lap_data.currentLapNum, lap_data.lapDistance,
                                  lap_data.totalDistance, lap_data.pitStatus, lap_data.resultStatus,
                                  lap_data.penalties))
        return result

    def read_next_packet(self):
        if self.next_packet is None:
            return False # End of stream

        (packet_timestamp, pkt_id, packet_id, packet_bytes) = self.next_packet
        packet = packets.unpack_udp_packet(packet_bytes)
        if packet_id == 1:
            self.safety_car_status = packet.safetyCarStatus

        if packet_id == 3:
            if packet.eventStringCode.decode() == "FTLP":
                self.fastest_lap_info = FastestLapInfo(self.get_current_race_duration(),
                                                       packet.eventDetails.fastestLap.lapTime,
                                                       packet.eventDetails.fastestLap.vehicleIdx)

            if packet.eventStringCode == "CHQF":
                self.chequered_flag = True

        if packet_id == 2:
            self.race_position = self.get_race_position(packet)

        self.next_packet = self.cursor.fetchone()
        if self.next_packet is None:
            self.cursor.close()

        return True

    def skip_to_first_race_position(self):
        if self.next_packet is None:
            return False # End of stream

        while self.race_position is None:
            if not self.read_next_packet():
                break
        return self.race_position is not None

    def skip_to_timestamp(self, timestamp):
        if self.next_packet is None:
            return False # End of stream

        if self.get_current_race_duration() > timestamp:
            return True

        while self.get_current_race_duration() <= timestamp:
            if not self.read_next_packet():
                return False

        return True

    def load_driver_names(self, driver_filename):
        if driver_filename is not None:
            with open(driver_filename) as file:
                driver_names_list = [line.strip() for line in file]
            return [name for name in driver_names_list if len(name) > 0]
        else:
            return []
