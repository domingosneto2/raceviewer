import session


class CarExtraInfo:
    def __init__(self, driver_id, team_id, number, is_active):
        self.lap_starts = [0]
        self.current_lap = 0
        self.car_info = None
        self.delta_ticks = 0
        self.progress = 0
        self.driver_id = driver_id
        self.team_id = team_id
        self.number = number
        self.is_active = is_active
        self.finished = False

    def update(self, car_info, leader_progress, lap_info, num_laps):
        if car_info.lap_number > self.current_lap:
            self.current_lap = car_info.lap_number
            self.lap_starts = car_info.timestamp
        self.car_info = car_info

        while leader_progress[self.delta_ticks][0] < self.car_info.total_distance \
                and self.delta_ticks < len(leader_progress) - 1:
            self.delta_ticks += 1

        leader_total_distance = leader_progress[-1][0]
        leader_timestamp = leader_progress[-1][1]
        leader_lap_distance = leader_progress[-1][2]
        curr_lap_info = lap_info[self.current_lap - 1]

        # If I'm in the same lap as the leader
        if self.car_info.lap_number == curr_lap_info.lap_number:
            leader_lap_time = leader_timestamp - curr_lap_info.start_timestamp
            leader_lap_pct = leader_lap_time / curr_lap_info.lap_duration
            t = self.interpolate(leader_progress, self.delta_ticks, self.car_info.total_distance)
            time_delta = leader_timestamp - t
            if leader_lap_time > 0:
                my_lap_pct = leader_lap_pct * (leader_lap_time - time_delta) / leader_lap_time
            else:
                my_lap_pct = 0
            self.progress = self.car_info.lap_number - 1 + my_lap_pct
        else:
            leader_lap_pct = 1
            leader_lap_time = lap_info[self.car_info.lap_number - 1].lap_duration
            t = self.interpolate(leader_progress, self.delta_ticks, self.car_info.total_distance)
            time_delta = lap_info[self.car_info.lap_number - 1].end_timestamp - t
            my_lap_pct = leader_lap_pct * (leader_lap_time - time_delta) / leader_lap_time
            self.progress = self.car_info.lap_number - 1 + my_lap_pct
        if self.progress < 0:
            self.progress = 0
        if self.progress > num_laps:
            self.progress = num_laps

    def interpolate(self, leader_progress, delta_ticks, total_distance):
        s1 = leader_progress[delta_ticks][0]
        s0 = leader_progress[delta_ticks - 1][0]
        t1 = leader_progress[delta_ticks][1]
        t0 = leader_progress[delta_ticks - 1][1]

        if s1 == s0:
            t = t1
        else:
            t = t1 - (s1 - total_distance) * (t1 - t0) / (s1 - s0)
        return t


class GameState:
    def __init__(self, fps, lap_duration):
        self.cars = []
        self.session = session.Session("/Users/dneto/dev/raceviewer/F1_2019_e9444ba7f05db735.sqlite3", "/Users/dneto/dev/raceviewer/driver_names.txt")
        self.num_laps = self.session.get_number_of_laps()
        self.track_length = self.session.get_track_length()
        self.session.start_race_replay()
        self.cars = self.session.get_current_race_position()
        self.participants = self.session.get_participants_info()
        self.lap_info = self.session.get_lap_info()
        self.leader_progress = []
        self.extra_info = [CarExtraInfo(car.driver_id, car.team_id, car.race_number, car.is_active) for car in self.participants]
        if self.lap_info[0].is_formation_lap():
            self.formation_lap = self.lap_info[0]
            del self.lap_info[0]
        self.current_frame = 0
        self.fps = fps
        self.frames_per_lap = fps * lap_duration
        self.total_frames = fps * lap_duration * self.num_laps
        self.current_timestamp = 0
        self.session_progress = 0
        self.safety_car = 0
        self.player_timestamp = 0
        self.chequered_flag = False
        self.pre_frames = 0
        self.fastest_lap = None
        self.post_frames = 0
        self.session_finished = False

    def next_frame(self):
        if self.pre_frames < self.frames_per_lap:
            self.pre_frames += 1
            return True

        if self.session_finished:
            if self.post_frames < self.frames_per_lap * 2:
                self.post_frames += 1
                return True
            else:
                return False

        self.current_frame += 1


        self.current_lap = int(self.current_frame / self.frames_per_lap)
        if self.current_lap >= len(self.lap_info):
            self.current_lap = len(self.lap_info) - 1
        current_lap_duration = self.lap_info[self.current_lap].lap_duration
        current_frame_in_lap = self.current_frame - self.frames_per_lap * self.current_lap
        progress_in_lap = float(current_frame_in_lap)/float(self.frames_per_lap)
        self.session_progress = (progress_in_lap + float(self.current_lap))/float(self.num_laps)
        self.current_timestamp = self.lap_info[self.current_lap].start_timestamp + current_lap_duration * progress_in_lap
        self.session_finished = not self.session.skip_to_timestamp(self.current_timestamp)
        self.safety_car = self.lap_info[self.current_lap].is_safety_car(self.current_timestamp)
        self.player_timestamp = float(self.current_frame) / float(self.fps)

        if self.current_lap >= self.num_laps:
            self.chequered_flag = True

        self.fastest_lap = self.lap_info[self.current_lap].get_fastest_lap(self.current_timestamp)

        next_frame_cars = self.session.get_current_race_position()
        for i in range(len(self.cars)):
            car = self.cars[i]
            next_car = next_frame_cars[i]
            extra_info = self.extra_info[i]

            if not extra_info.finished:
                if next_car.lap_number > car.lap_number and self.chequered_flag or next_car.lap_number > self.num_laps:
                    extra_info.finished = True
                else:
                     self.cars[i] = next_car
            else:
                self.cars[i].position = next_car.position

        self.update_leader_progress()

        for i in range(len(self.extra_info)):
            self.extra_info[i].update(self.cars[i], self.leader_progress, self.lap_info, self.num_laps)

        return True


    def update_leader_progress(self):
        leader = [car for car in self.cars if car.position == 1][0]
        self.leader_progress.append((leader.total_distance, leader.timestamp, leader.lap_distance))









