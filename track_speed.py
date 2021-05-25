

class RaceEvent:
    def __init__(self, start_time, start_distance):
        self.start_time = start_time
        self.start_distance = start_distance
        self.end_time = None
        self.end_distance = None

    def end(self, time, distance):
        self.end_time = time
        self.end_distance = distance

    def is_happening(self):
        return self.end_time is None

    def duration(self):
        return self.end_time - self.start_time


class RaceEvents:
    def __init__(self, car_idx, min_duration = 0.0):
        self.car_idx = car_idx
        self.events = []
        self.min_duration = min_duration

    def record(self, timestamp, race_distance, is_happening):
        if is_happening:
            if len(self.events) == 0 or not self.events[-1].is_happening():
                self.events.append(RaceEvent(timestamp, race_distance))
        else:
            if len(self.events) != 0 and self.events[-1].is_happening():
                self.events[-1].end(timestamp, race_distance)
                if self.events[-1].duration() < self.min_duration:
                    del self.events[-1]

    def is_happening(self, timestamp):
        for event in self.events:
            if event.start_time > timestamp:
                return False

            if event.end_time >= timestamp:
                return True


class TrackSpeed:
    def __init__(self, session):
        track_length = session.get_track_length()
        self.num_laps = session.get_number_of_laps()
        self.bins = [0.0] * (track_length + 1)
        self.counts = [0.0] * (track_length + 1)

        self.spins = None
        self.pits = None

        self.participants = session.get_participants_info()

        self.compute_average_speed(session)

        self.find_spins(session)

    def compute_average_speed(self, session):
        session.start_race_replay(True)
        previous_position = session.get_current_race_position()

        while session.read_next_packet():
            position = session.get_current_race_position()
            if position is None:
                continue
            if previous_position is not None:
                for i, car in enumerate(position):
                    if not self.participants[i].is_active:
                        continue
                    if car.lap_number > 1 and car.lap_number < self.num_laps and car.pit_status == 0:
                        # Compute speed
                        previous = previous_position[i]
                        delta_t = car.timestamp - previous.timestamp
                        if delta_t > 0:
                            speed = (car.lap_distance - previous.lap_distance) / (car.timestamp - previous.timestamp)
                            bucket = int(car.lap_distance)
                            self.bins[bucket] += speed
                            self.counts[bucket] += 1
            previous_position = position

    def is_spin(self, car, previous):
        delta_t = car.timestamp - previous.timestamp
        if delta_t == 0:
            return False
        speed = (car.lap_distance - previous.lap_distance) / delta_t
        bucket = int(car.lap_distance)
        average_speed = self.bins[bucket] / self.counts[bucket]
        return speed < average_speed * 0.5

    def find_spins(self, session):
        session.start_race_replay(True)
        previous_position = session.get_current_race_position()

        self.spins = []
        self.pits = []
        for i in range(len(self.participants)):
            self.spins.append(RaceEvents(i, 0.2))
            self.pits.append(RaceEvents(i))

        while session.read_next_packet():
            position = session.get_current_race_position()
            if position is None:
                continue
            if previous_position is not None:
                for i, car in enumerate(position):
                    if not self.participants[i].is_active:
                        continue
                    is_pits = car.pit_status != 0
                    self.pits[i].record(car.timestamp, car.total_distance, is_pits)
                    if car.lap_number > 1 and car.lap_number < self.num_laps:
                        # Compute speed
                        is_spinning = self.is_spin(car, previous_position[i]) and not is_pits
                        self.spins[i].record(car.timestamp, car.total_distance, is_spinning)
            previous_position = position

        # Clear 'spins' going in or coming out of pit stop
        for i in range(len(self.spins)):
            car_spins = self.spins[i]
            car_pits = self.pits[i]

            for spin in car_spins.events:
                if car_pits.is_happening(spin.start_time - 5) \
                        or car_pits.is_happening(spin.end_time + 2) \
                        or car_pits.is_happening(spin.start_time) \
                        or car_pits.is_happening(spin.end_time):
                    spin.end_time = spin.start_time

            car_spins.events = [e for e in car_spins.events if e.start_time != e.end_time]

    def is_spinning(self, car, timestamp):
        return self.spins[car].is_happening(timestamp)
