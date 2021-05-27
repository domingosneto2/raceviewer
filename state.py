import session
import track_speed


class CarState:
    def __init__(self, car_idx, state):
        self.delta_index = 0
        self.progress = 0
        self.car_idx = car_idx
        self.finished = False
        self.state = state
        self.is_spinning = False

    def driver_name(self):
        return self.participant_info().driver_name

    def participant_info(self):
        return self.state.participants[self.car_idx]

    def car_info(self):
        return self.state.cars[self.car_idx]

    def team_id(self):
        return self.participant_info().team_id

    def is_active(self):
        return self.participant_info().is_active

    def position(self):
        return self.car_info().position

    def pit_status(self):
        return self.car_info().pit_status

    def final_classification(self):
        return self.state.final_classification[self.car_idx]

    def leader_final_classification(self):
        return [c for c in self.state.final_classification if c.position == 1][0]

    def final_time_with_penalties(self):
        return self.final_classification().final_time_with_penalties()

    def update(self, leader_progress, lap_info, num_laps, session_lap):
        car_info = self.state.cars[self.car_idx]
        current_lap = car_info.lap_number

        self.is_spinning = self.state.speed_info.is_spinning(self.car_idx, car_info.timestamp)
        self.is_spinning = self.is_spinning and not self.state.is_safety_car()

        while leader_progress[self.delta_index][0] < car_info.total_distance \
                and self.delta_index < len(leader_progress) - 1:
            self.delta_index += 1

        leader_timestamp = leader_progress[-1][1]
        curr_lap_info = lap_info[current_lap - 1]

        # If I'm in the same lap as the leader
        if current_lap == session_lap:
            leader_lap_time = leader_timestamp - curr_lap_info.start_timestamp
            leader_lap_pct = leader_lap_time / curr_lap_info.lap_duration
            t = self.interpolate(leader_progress, self.delta_index, car_info.total_distance)
            time_delta = leader_timestamp - t
            if leader_lap_time > 0:
                my_lap_pct = leader_lap_pct * (leader_lap_time - time_delta) / leader_lap_time
            else:
                my_lap_pct = 0
            self.progress = car_info.lap_number - 1 + my_lap_pct
        else:
            leader_lap_pct = 1
            leader_lap_time = lap_info[car_info.lap_number - 1].lap_duration
            t = self.interpolate(leader_progress, self.delta_index, car_info.total_distance)
            time_delta = lap_info[car_info.lap_number - 1].end_timestamp - t
            my_lap_pct = leader_lap_pct * (leader_lap_time - time_delta) / leader_lap_time
            self.progress = car_info.lap_number - 1 + my_lap_pct
        if self.progress < 0:
            self.progress = 0
        if self.progress > num_laps:
            self.progress = num_laps

    def interpolate(self, leader_progress, delta_index, total_distance):
        s1 = leader_progress[delta_index][0]
        s0 = leader_progress[delta_index - 1][0]
        t1 = leader_progress[delta_index][1]
        t0 = leader_progress[delta_index - 1][1]

        if s1 == s0:
            t = t1
        else:
            t = t1 - (s1 - total_distance) * (t1 - t0) / (s1 - s0)
        return t


class GameState:
    def __init__(self, session, fps, lap_duration, start_frame=0):
        self.cars = []
        self.session = session
        self.num_laps = self.session.get_number_of_laps()
        self.track_length = self.session.get_track_length()
        self.final_classification = self.session.get_final_classification()

        self.speed_info = track_speed.TrackSpeed(self.session)

        self.session.start_race_replay(skip_formation_lap=True)
        self.session.skip_to_first_race_position()
        self.cars = self.session.get_current_race_position()
        self.participants = self.session.get_participants_info()
        self.lap_info = self.session.get_lap_info()
        self.car_states = [CarState(i, self) for (i, car) in enumerate(self.participants)]
        if self.lap_info[0].is_formation_lap():
            self.formation_lap = self.lap_info[0]
            del self.lap_info[0]
        self.current_frame = start_frame
        self.current_lap = 0
        self.fps = fps
        self.frames_per_lap = fps * lap_duration
        self.total_frames = fps * lap_duration * self.num_laps
        self.current_timestamp = 0
        self.session_progress = 0
        self.player_timestamp = 0
        if start_frame == 0:
            self.pre_frames = 0
        else:
            # Don't wait if we're skipping frames
            self.pre_frames = self.frames_per_lap
        self.post_frames = 0
        self.session_finished = False
        self.leader_progress = []
        self.is_chequered_flag = False

    def car_state(self, index):
        return self.car_states[index]

    def is_safety_car(self):
        return not self.session.safety_car_status == 0

    def fastest_lap(self):
        return self.session.fastest_lap_info

    def chequered_flag(self):
        return self.is_chequered_flag

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
        self.is_chequered_flag = self.current_lap >= self.num_laps
        if self.current_lap >= self.num_laps:
            self.current_lap = self.num_laps - 1
        current_lap_duration = self.lap_info[self.current_lap].lap_duration
        current_frame_in_lap = self.current_frame - self.frames_per_lap * self.current_lap
        progress_in_lap = float(current_frame_in_lap)/float(self.frames_per_lap)
        self.session_progress = (progress_in_lap + float(self.current_lap))/float(self.num_laps)
        self.current_timestamp = self.lap_info[self.current_lap].start_timestamp + current_lap_duration * progress_in_lap
        self.session_finished = not self.session.skip_to_timestamp(self.current_timestamp)
        self.player_timestamp = float(self.current_frame) / float(self.fps)

        next_frame_cars = self.session.get_current_race_position()
        for i in range(len(self.cars)):
            car = self.cars[i]
            next_car = next_frame_cars[i]
            car_state = self.car_states[i]

            if not car_state.finished:
                if next_car.lap_number > car.lap_number and self.chequered_flag() or next_car.lap_number > self.num_laps:
                    car_state.finished = True
                else:
                     self.cars[i] = next_car
            else:
                self.cars[i].position = next_car.position

        self.update_leader_progress()

        for i in range(len(self.car_states)):
            self.car_states[i].update(self.leader_progress, self.lap_info, self.num_laps, self.current_lap)

        return True

    def update_leader_progress(self):
        leader = [car for car in self.cars if car.position == 1][0]
        self.leader_progress.append((leader.total_distance, leader.timestamp, leader.lap_distance))









