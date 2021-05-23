import pygame.locals

# WINDOW_HEIGHT = 1080
# WINDOW_WIDTH = 1940
WINDOW_HEIGHT=480
WINDOW_WIDTH=720
FPS = 60

FONT_SIZE_FACTOR=WINDOW_HEIGHT/1080

# CAR_FONT_SIZE=18
# INFO_FONT_SIZE=50
# TRACK_FONT_SIZE=30

CAR_FONT_SIZE_BASE=36
INFO_FONT_SIZE_BASE=100
TRACK_FONT_SIZE_BASE=60


CAR_FONT_SIZE=int(CAR_FONT_SIZE_BASE*FONT_SIZE_FACTOR)
INFO_FONT_SIZE=int(INFO_FONT_SIZE_BASE * FONT_SIZE_FACTOR)
TRACK_FONT_SIZE=int(TRACK_FONT_SIZE_BASE * FONT_SIZE_FACTOR)

TOP_BORDER = WINDOW_HEIGHT / 10
BOTTOM_BORDER = WINDOW_HEIGHT / 20
LEFT_BORDER = WINDOW_WIDTH / 20
RIGHT_BORDER = WINDOW_WIDTH / 20

CAR_SPACING = 0.5

TRACK_HEIGHT = WINDOW_HEIGHT - TOP_BORDER - BOTTOM_BORDER
VISIBLE_TRACK_WIDTH = WINDOW_WIDTH - LEFT_BORDER - RIGHT_BORDER

CAR_WIDTH = (WINDOW_HEIGHT - TOP_BORDER - BOTTOM_BORDER) / (20 + 19 * CAR_SPACING)
CAR_LENGTH = CAR_WIDTH * 2

VIEWPORT_INITIAL_X = -LEFT_BORDER - CAR_LENGTH

LAPS_PER_SCREEN = 3
LAP_WIDTH = VISIBLE_TRACK_WIDTH / LAPS_PER_SCREEN

SECONDS_PER_LAP = 2

POSITION_CHANGE_DURATION = 0.5


class Car:
    def __init__(self, car_index, game_state, renderer):
        self.car_index = car_index
        self.game_state = game_state
        self.surf = pygame.Surface((CAR_LENGTH, CAR_WIDTH))
        self.color = self.get_color(game_state.extra_info[car_index].team_id)
        self.surf.fill(self.color)
        self.rect = self.surf.get_rect()
        self.renderer = renderer
        self.name = f"[{game_state.cars[car_index].driver_name}]"
        # lap_text_img = self.lap_font.render(lap_text, True, (255, 255, 255))
        self.name_img = renderer.driver_font.render(self.name, True, (255, 255, 0))
        self.name_pit_img = renderer.driver_font.render(self.name + "[PIT]", True, (255, 255, 0))
        self.position_queue = [0]
        self.penalties_img = None
        self.penalties = 0
        self.last_position_change = 0
        self.renderer = renderer

    def is_active(self):
        return self.game_state.extra_info[self.car_index].is_active

    def get_color(self, team_id):
        if team_id == 0:
            return 0,210,190
        if team_id == 1:
            return 192,0,0
        if team_id == 2:
            return 6,0,239
        if team_id == 3:
            return 0,130,250
        if team_id == 4:
            return 245,150,200
        if team_id == 5:
            return 255,245,0
        if team_id == 6:
            return 200,200,200
        if team_id == 7:
            return 120,120,120
        if team_id == 8:
            return 255,135,0
        if team_id == 9:
            return 150,0,0

    def process_position_change(self, player_timestamp):
        position = self.game_state.cars[self.car_index].position
        if len(self.position_queue) == 1 and self.position_queue[0] == 0:
            self.position_queue[0] = position
            self.last_position_change = 0
            return

        if self.position_queue[-1] != position:
            if len(self.position_queue) == 1:
                self.position_queue.append(position)
                self.last_position_change = player_timestamp
            else:
                self.position_queue[0] = self.get_position_for_rendering(player_timestamp)
                self.position_queue[1] = position
                self.last_position_change = player_timestamp

        if self.get_position_change_progress(player_timestamp) == 1 and len(self.position_queue) > 1:
            del self.position_queue[0]
            if len(self.position_queue) > 1:
                self.last_position_change = player_timestamp

    def update(self, player_timestamp):
        self.process_position_change(player_timestamp)
        car = self.game_state.cars[self.car_index]

        if self.penalties != car.penalties:
            self.penalties = car.penalties
            if self.penalties > 0:
                penalties_msg = f"[+{self.penalties}]"
                self.penalties_img = self.renderer.driver_font.render(penalties_msg, True, (255, 255, 255))
            else:
                self.penalties_img = None


    def get_position_change_progress(self, player_timestamp):
        position_change_speed = POSITION_CHANGE_DURATION
        if self.last_position_change > (player_timestamp - position_change_speed):
            return (player_timestamp - self.last_position_change) / position_change_speed
        else:
            return 1

    def get_current_position_for_z_order(self):
        return self.position_queue[-1]

    def get_position_for_rendering(self, player_timestamp):
        if len(self.position_queue) == 1:
            return self.position_queue[0]
        position_change_progress = self.get_position_change_progress(player_timestamp)
        result = float(self.position_queue[1]) - float((self.position_queue[1] - self.position_queue[0])) * (1.0 - position_change_progress)
        return result

    def draw(self, surface, viewport_position, player_timestamp):
        car_info = self.game_state.extra_info[self.car_index]
        car = self.game_state.cars[self.car_index]
        progress = car_info.progress / self.game_state.num_laps
        position = self.get_position_for_rendering(player_timestamp)
        self.rect.top = TOP_BORDER + (position - 1) * CAR_WIDTH * (1 + CAR_SPACING)
        self.rect.right = progress * LAP_WIDTH * self.game_state.num_laps - viewport_position
        surface.blit(self.surf, self.rect)
        if car.pit_status == 0:
            img_to_render = self.name_img
        else:
            img_to_render = self.name_pit_img
        name_rect = img_to_render.get_rect()
        name_rect.centery = self.rect.centery
        name_rect.left = self.rect.right + 5
        surface.blit(img_to_render, name_rect)

        if self.penalties_img is not None:
            penalties_img_rect  = self.penalties_img.get_rect()
            penalties_img_rect.centery = self.rect.centery
            penalties_img_rect.right = self.rect.left - 5
            surface.blit(self.penalties_img, penalties_img_rect)

        fl = self.game_state.fastest_lap
        if fl is not None and fl.driver_idx == self.car_index:
            fl_rect = self.renderer.fl_img.get_rect()
            fl_rect.centery = self.rect.centery
            fl_rect.left = name_rect.right + 5
            surface.blit(self.renderer.fl_img, fl_rect)






class Renderer:
    def __init__(self, caption, state):
        pygame.init()
        self.driver_font = pygame.font.SysFont(None, CAR_FONT_SIZE)
        self.info_font = pygame.font.SysFont(None, INFO_FONT_SIZE)
        self.lap_font = pygame.font.SysFont(None, TRACK_FONT_SIZE)
        self.state = state
        self.displaysurface = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.viewport_position = 0
        pygame.display.set_caption(caption)
        self.cars = []
        for i in range(len(state.cars)):
            self.cars.append( Car(i, state, self))
        self.fl_img = self.driver_font.render("FL", True, (255, 255, 255))
        self.fl_surf = pygame.Surface((self.fl_img.get_rect().width, CAR_WIDTH))
        self.fl_surf.fill((0, 0, 0))
        rect = self.fl_img.get_rect()
        rect.center = self.fl_surf.get_rect().center
        self.fl_surf.blit(self.fl_img, rect)
        self.fl_img = self.fl_surf
        self.right_side_space = self.extra_right_space()

    def max_name_width(self):
        return max([car.name_img.get_rect().width for car in self.cars])

    def extra_right_space(self):
        return self.max_name_width() + self.fl_img.get_rect().width + 20

    def update_viewport(self, session_progress):
        initial_viewport_position = VIEWPORT_INITIAL_X
        final_viewport_position = LAP_WIDTH * self.state.num_laps - WINDOW_WIDTH + max(RIGHT_BORDER, self.right_side_space)
        return initial_viewport_position + session_progress * (final_viewport_position - initial_viewport_position)

    def update(self):
        self.displaysurface.fill((160, 160, 160))
        progress = self.state.session_progress
        if progress > 1:
            progress = 1
        self.viewport_position = self.update_viewport(progress)
        self.draw_track(self.displaysurface)

        for car in self.cars:
            car.update(self.state.player_timestamp)
        sorted_cars = sorted(self.cars, key=lambda c: -c.get_current_position_for_z_order())
        for car in sorted_cars:
            if car.is_active():
                car.draw(self.displaysurface, self.viewport_position, self.state.player_timestamp)

        if self.state.safety_car:
            info_text = f"[SC]"
            img = self.info_font.render(info_text, True, (255, 255, 0))
            self.displaysurface.blit(img, (5, 5))

    def draw_track(self, surface):
        for i in range(0, self.state.num_laps + 1):
            lap_x = i * LAP_WIDTH - self.viewport_position
            if -LAP_WIDTH < lap_x < WINDOW_WIDTH + LAP_WIDTH:
                pygame.draw.line(surface, (255, 255, 255), (lap_x, 0), (lap_x, WINDOW_HEIGHT), 4)
                if i < self.state.num_laps + 1:
                    lap_text = f"Lap {i+1}"
                    lap_text_img = self.lap_font.render(lap_text, True, (255, 255, 255))
                    self.displaysurface.blit(lap_text_img, (lap_x + 10, 5))
