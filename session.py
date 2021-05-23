import sqlite3
import f1_2020_telemetry.packets as packets

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
    def __init__(self, lap_number, start_timestamp, pkt_id, previous_lap_info=None):
        self.lap_number = lap_number
        self.start_timestamp = start_timestamp
        self.end_timestamp = None
        self.lap_duration = None
        self.events = []
        self.safety_car_events = []
        self.pkt_id = pkt_id
        if previous_lap_info is not None:
            self.starting_safety_car_state = previous_lap_info.ending_safety_car_state()
            self.fastest_lap = previous_lap_info.ending_fastest_lap_info()
        else:
            self.starting_safety_car_state = 0
            self.fastest_lap = []

    def add_event(self, packet):
        self.events.append(packet)
        if packet.eventStringCode.decode() == "FTLP":
            self.fastest_lap.append(FastestLapInfo(packet.header.sessionTime, packet.eventDetails.fastestLap.lapTime, packet.eventDetails.fastestLap.vehicleIdx))

    def ending_fastest_lap_info(self):
        if len(self.fastest_lap) > 0:
            return self.fastest_lap[-1:]
        return []

    def get_fastest_lap(self, timestamp):
        candidates = [fl for fl in self.fastest_lap if fl.timestamp <= timestamp]
        if len(candidates) == 0:
            return None
        return candidates[-1]


    def ending_safety_car_state(self):
        if len(self.safety_car_events) == 0:
            return self.starting_safety_car_state
        else:
            return self.safety_car_events[-1].status

    def set_end_timestamp(self, end_timestmap):
        self.end_timestamp = end_timestmap
        self.lap_duration = self.end_timestamp - self.start_timestamp

    def add_safety_car_event(self, status, timestamp):
        if len(self.safety_car_events) == 0 or self.safety_car_events[-1].status != status:
            self.safety_car_events.append(SafetyCarEvent(status, timestamp))

    def is_formation_lap(self):
        return len([e for e in self.safety_car_events if e.status == 3]) > 0

    def is_safety_car(self, timestamp):
        is_safety_car = self.starting_safety_car_state != 0
        for event in self.safety_car_events:
            if event.timestamp > timestamp:
                break
            is_safety_car = event.status != 0
        return is_safety_car

    def is_chequered_flag(self, timestamp):
        for event in self.events:
            if event.eventStringCode == "CHQF":
                if timestamp >= event.header.sessionTime:
                    return True
            if event.header.sessionTime > timestamp:
                return False
        return False

    def __repr__(self):
        return str(vars(self))



class Session:
    def __init__(self, filename, driver_filename):
        self.filename = filename
        self.conn = sqlite3.connect(filename)
        self.replay_cursor = None
        self.driver_names = self.load_driver_names(driver_filename)
        pass

    def get_track_length(self):
        cursor = self.conn.cursor()
        query = "SELECT timestamp, packet FROM packets WHERE packetId = 1 ORDER BY pkt_id;"
        cursor.execute(query)

        timestamped_packet = cursor.fetchone()
        (timestamp, packet_bytes) = timestamped_packet
        packet = packets.unpack_udp_packet(packet_bytes)
        cursor.close()
        return packet.trackLength

    def get_participants_info(self):
        cursor = self.conn.cursor()
        query = "SELECT timestamp, packet FROM packets WHERE packetId = 4 ORDER BY pkt_id;"
        cursor.execute(query)

        timestamped_packet = cursor.fetchone()
        (timestamp, packet_bytes) = timestamped_packet
        packet = packets.unpack_udp_packet(packet_bytes)
        cursor.close()
        participants = [ParticipantInfo(p.driverId, p.teamId, p.raceNumber) for p in packet.participants]
        for i in range(len(participants)):
            participants[i].is_active = i < packet.numActiveCars
        return participants

    def get_number_of_laps(self):
        cursor = self.conn.cursor()
        query = "SELECT timestamp, packet FROM packets WHERE packetId = 1 ORDER BY pkt_id;"
        cursor.execute(query)

        timestamped_packet = cursor.fetchone()
        (timestamp, packet_bytes) = timestamped_packet
        packet = packets.unpack_udp_packet(packet_bytes)
        cursor.close()
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
                if current_lap_info and not current_lap_info.is_formation_lap():
                    del lap_infos[-1]
                current_lap_info = LapInfo(1, timestamp, pkt_id)
                lap_infos.append(current_lap_info)
                current_lap = 1

            if packetId == 3 and packet.eventStringCode.decode() == "SEND":
                current_lap_info.set_end_timestamp(timestamp)

            if packetId == 2:
                packet_lap = max([d.currentLapNum for d in packet.lapData])
                if packet_lap > current_lap:
                    current_lap_info.set_end_timestamp(timestamp)
                    current_lap_info = LapInfo(packet_lap, timestamp, pkt_id, current_lap_info)
                    lap_infos.append(current_lap_info)
                    current_lap = packet_lap

            if packetId == 1:
                current_lap_info.add_safety_car_event(packet.safetyCarStatus, timestamp)

            if packetId == 3:
                 current_lap_info.add_event(packet)

            timestamped_packet = cursor.fetchone()
        current_lap_info.set_end_timestamp(timestamp)
        cursor.close()

        return lap_infos

    def get_starting_positions(self):

        cursor = self.conn.cursor()
        query = "SELECT sessionTime, pkt_id, packetId, packet FROM packets WHERE packetId = 2 ORDER BY pkt_id;"
        cursor.execute(query)
        timestamped_packet = cursor.fetchone()
        (timestamp, pkt_id, packetId, packet_bytes) = timestamped_packet
        packet = packets.unpack_udp_packet(packet_bytes)
        cursor.close()
        return self.get_race_position(packet, timestamp)

    def start_race_replay(self):
        lap_infos = self.get_lap_info()
        lap_infos = [lap_info for lap_info in lap_infos if not lap_info.is_formation_lap()]
        start_pkt_id = lap_infos[0].pkt_id
        self.cursor = self.conn.cursor()
        query = f"SELECT sessionTime, pkt_id, packetId, packet FROM packets WHERE packetId = 2 AND pkt_id >= {start_pkt_id} ORDER BY pkt_id"
        self.cursor.execute(query)
        self.current_packet = self.cursor.fetchone()
        (timestamp, pkt_id, packetId, packet_bytes) = self.current_packet

    def get_current_race_position(self):
        (timestamp, pkt_id, packetId, packet_bytes) = self.current_packet
        packet = packets.unpack_udp_packet(packet_bytes)
        return self.get_race_position(packet, timestamp)

    def get_race_position(self, packet, timestamp):
        result = []
        for i in range(len(packet.lapData)):
            lap_data = packet.lapData[i]
            position = lap_data.gridPosition
            if position < 1 or position > len(self.driver_names):
                driver_name = ""
            else:
                driver_name = self.driver_names[position - 1]
            result.append(CarInfo(timestamp, lap_data.carPosition, lap_data.currentLapNum, lap_data.lapDistance,
                                  lap_data.totalDistance, driver_name, lap_data.pitStatus, lap_data.resultStatus,
                                  lap_data.penalties))
        return result

    def skip_to_timestamp(self, timestamp):
        (packet_timestamp, pkt_id, packetId, packet_bytes) = self.current_packet
        if packet_timestamp > timestamp:
            return True

        while packet_timestamp < timestamp:
            next_packet = self.cursor.fetchone()
            if next_packet:
                (packet_timestamp, pkt_id, packetId, packet_bytes) = next_packet
                self.current_packet = next_packet
            else:
                return False

        return True


    def dump_lap_data_packets(self):
        cursor = self.conn.cursor()
        query = "SELECT sessionTime, pkt_id, packetId, packet FROM packets WHERE packetId in (1, 2, 3) ORDER BY pkt_id;"
        cursor.execute(query)

        timestamped_packet = cursor.fetchone()
        first_timestamp = timestamped_packet[0]
        current_lap = -999
        # current_lap = max([d.currentLapNum for d in  packet.lapData])
        num_packets = 0

        while timestamped_packet is not None:
            (timestamp, pkt_id, packetId, packet_bytes) = timestamped_packet
            packet = packets.unpack_udp_packet(packet_bytes)

            if packetId == 1:
                print(f"{pkt_id} {timestamp} {packetId} {packet.sessionType} {packet.sessionTimeLeft} {packet.safetyCarStatus}")
                pass
            elif packetId == 3:
                print(f"{pkt_id} {timestamp} {packetId} {packet.eventStringCode} {packet}")
            else:
                packet_lap = max([d.currentLapNum for d in packet.lapData])
                max_distance = max([d.lapDistance for d in packet.lapData])
                elapsed = timestamp - first_timestamp

                # print(f"{pkt_id} {elapsed} {max_distance}")
                if packet_lap != current_lap:
                    print(f"{pkt_id} {timestamp} {packetId} {packet_lap} {num_packets}")
                    current_lap = packet_lap
                    num_packets = 1
                num_packets += 1

            timestamped_packet = cursor.fetchone()

        print(f"{pkt_id} {timestamp} {packet_lap} {num_packets}")
        cursor.close()

    def load_driver_names(self, driver_filename):
        with open(driver_filename) as file:
            driver_names_list = [line.strip() for line in file]
        return [name for name in driver_names_list if len(name) > 0]
