import sqlite3
import f1_2020_telemetry.packets as packets


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
    def __init__(self, driver_id, team_id, race_number):
        self.driver_id = driver_id
        self.team_id = team_id
        self.race_number =race_number
        self.is_active = True


class CarInfo:
    def __init__(self, timestamp, position, lap_number, lap_distance, total_distance, driver_name, pit_status,
                 result_status, penalties):
        self.timestamp = timestamp
        self.position = position
        self.lap_number = lap_number
        self.lap_distance = lap_distance
        self.total_distance = total_distance
        self.driver_name = driver_name
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


class LapInfo:
    def __init__(self, lap_number, start_timestamp, pkt_id):
        self.lap_number = lap_number
        self.start_timestamp = start_timestamp
        self.end_timestamp = None
        self.lap_duration = None
        self.events = []
        self.safety_car_events = []
        self.start_pkt_id = pkt_id
        self.end_pkt_id = None

    def add_event(self, packet):
        self.events.append(packet)

    def end_lap(self, end_timestamp, end_pkt_id):
        self.end_timestamp = end_timestamp
        self.lap_duration = self.end_timestamp - self.start_timestamp
        self.end_pkt_id = end_pkt_id

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
        self.driver_names = self.load_driver_names(driver_filename)

        self.safety_car_status = None
        self.fastest_lap_info = None
        self.race_position = None
        self.chequered_flag = None
        self.active_participants = [p for p in self.get_participants_info() if p.is_active]

        self.next_timestamp = None
        self.next_packet = None

        self.laps = None
        self.cursor = None

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
        participants = [ParticipantInfo(p.driverId, p.teamId, p.raceNumber) for p in packet.participants]
        for i in range(len(participants)):
            participants[i].is_active = i < packet.numActiveCars
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
                    del lap_infos[-1]

                current_lap_info = LapInfo(1, timestamp, pkt_id)
                lap_infos.append(current_lap_info)
                current_lap = 1

            if packetId == 3 and packet.eventStringCode.decode() == "SEND":
                current_lap_info.end_lap(timestamp, pkt_id)

            if packetId == 2:
                packet_lap = max([d.currentLapNum for d in packet.lapData])
                if packet_lap > current_lap:
                    current_lap_info.end_lap(timestamp, pkt_id)
                    current_lap_info = LapInfo(packet_lap, timestamp, pkt_id)
                    lap_infos.append(current_lap_info)
                    current_lap = packet_lap

            # Need this to track if the lap is a formation lap
            if packetId == 1:
                current_lap_info.add_safety_car_event(packet.safetyCarStatus, timestamp)

            if packetId == 3:
                current_lap_info.add_event(packet)

            timestamped_packet = cursor.fetchone()
        current_lap_info.end_lap(timestamp, pkt_id)
        cursor.close()

        return lap_infos

    def start_race_replay(self, skip_formation_lap):
        self.laps = self.get_lap_info()
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
        self.next_timestamp = None if self.next_packet is None else self.next_packet[0]

    def get_current_race_position(self):
        return self.race_position

    def get_race_position(self, packet):
        result = []
        for i in range(len(packet.lapData)):
            lap_data = packet.lapData[i]
            position = lap_data.gridPosition
            if position < 1 or position > len(self.driver_names):
                driver_name = ""
            else:
                driver_name = self.driver_names[position - 1]
            result.append(CarInfo(packet.header.sessionTime, lap_data.carPosition, lap_data.currentLapNum, lap_data.lapDistance,
                                  lap_data.totalDistance, driver_name, lap_data.pitStatus, lap_data.resultStatus,
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
                self.fastest_lap_info = FastestLapInfo(packet.header.sessionTime,
                                                       packet.eventDetails.fastestLap.lapTime,
                                                       packet.eventDetails.fastestLap.vehicleIdx)

            if packet.eventStringCode == "CHQF":
                self.chequered_flag = True

        if packet_id == 2:
            self.race_position = self.get_race_position(packet)

        self.next_packet = self.cursor.fetchone()
        if self.next_packet is not None:
            self.next_timestamp = self.next_packet[0]
        else:
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

        if self.next_timestamp > timestamp:
            return True

        while self.next_timestamp <= timestamp:
            if not self.read_next_packet():
                return False

        return True

    def load_driver_names(self, driver_filename):
        with open(driver_filename) as file:
            driver_names_list = [line.strip() for line in file]
        return [name for name in driver_names_list if len(name) > 0]
