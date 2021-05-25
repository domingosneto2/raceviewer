import pygame.locals
import text
import math

WINDOW_HEIGHT = 1080
WINDOW_WIDTH = 1940
# WINDOW_HEIGHT=480
# WINDOW_WIDTH=720
FPS = 60

SCALE_FACTOR= WINDOW_HEIGHT / 1080

CAR_FONT_SIZE_BASE=26
INFO_FONT_SIZE_BASE=100
TRACK_FONT_SIZE_BASE=60

TEXT_BOX_BORDER_BASE=5


CAR_FONT_SIZE=int(CAR_FONT_SIZE_BASE * SCALE_FACTOR)
INFO_FONT_SIZE=int(INFO_FONT_SIZE_BASE * SCALE_FACTOR)
TRACK_FONT_SIZE=int(TRACK_FONT_SIZE_BASE * SCALE_FACTOR)

TEXT_BOX_BORDER=int(TEXT_BOX_BORDER_BASE * SCALE_FACTOR)

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

WHITE=(255, 255, 255)
BLACK=(0, 0, 0)
YELLOW=(255, 255, 0)
FL_PURPLE=(202, 155, 247)

SPIN_ANIMATION_DURATION = 0.5

class Car:
    def __init__(self, car_index, renderer):
        self.car_index = car_index
        self.renderer = renderer

        self.color = self.get_color(self.car_state().team_id())
        self.rect = pygame.Rect(0, 0, CAR_LENGTH, CAR_WIDTH)

        self.name = renderer.state.cars[car_index].driver_name
        self.position_queue = [0]
        self.penalties_img = None
        self.penalties = 0
        self.last_position_change = 0
        self.renderer = renderer

        self.spin_start_timestamp = 0
        self.spin_end_timestamp = 0
        # Rotation is such that 0 means no rotation, 0.5 means 180 degrees or
        # PI rads, and 1 means 360 degrees or 2xPI rads
        self.rotation = 0

    def car_state(self):
        return self.renderer.state.car_state(self.car_index)

    def get_base_name_width(self):
        return text.prepare_text(self.name, self.renderer.driver_font, BLACK).get_rect().width

    def prepare_name_surfaces(self, width):
        self.name_surface = text.prepare_text(self.name, self.renderer.driver_font, WHITE, BLACK, width, CAR_WIDTH, TEXT_BOX_BORDER)
        self.fl_name_surface = text.prepare_text(self.name, self.renderer.driver_font, WHITE, FL_PURPLE, width, CAR_WIDTH, TEXT_BOX_BORDER)

    def is_active(self):
        return self.car_state().is_active()

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
        position = self.car_state().position()
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

        self.update_rotation_angle(player_timestamp)

        car = self.renderer.state.cars[self.car_index]

        if self.penalties != car.penalties:
            self.penalties = car.penalties
            if self.penalties > 0:
                penalties_msg = f"[+{self.penalties}]"
                self.penalties_img = self.renderer.driver_font.render(penalties_msg, True, (255, 255, 255))
            else:
                self.penalties_img = None

    def update_rotation_angle(self, player_timestamp):
        car_state = self.car_state()
        if car_state.is_spinning and self.spin_start_timestamp == 0:
            self.spin_start_timestamp = player_timestamp
            self.spin_end_timestamp = 0
        if car_state.is_spinning and self.spin_end_timestamp != 0:
            self.spin_end_timestamp = 0
        if not car_state.is_spinning and self.spin_start_timestamp != 0 and self.spin_end_timestamp == 0:
            self.spin_end_timestamp = player_timestamp

        if self.spin_end_timestamp != 0:
            spin_elapsed = self.spin_end_timestamp - self.spin_start_timestamp
            target_rotation_end = math.ceil(spin_elapsed / SPIN_ANIMATION_DURATION) * SPIN_ANIMATION_DURATION
            if player_timestamp >= self.spin_start_timestamp + target_rotation_end:
                self.rotation = 0
                self.spin_start_timestamp = 0
                self.spin_end_timestamp = 0

        self.rotation = (player_timestamp - self.spin_start_timestamp) / SPIN_ANIMATION_DURATION

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

    def get_polygon(self, player_timestamp):
        points = (self.rect.topleft, self.rect.topright, self.rect.bottomright, self.rect.bottomleft)
        if self.spin_start_timestamp:
            points = self.rotate_around_center(points, self.rotation, self.rect)
        return points

    def rotate_around_center(self, points, rotation_amount, rect):
        translation = (-rect.centerx, -rect.centery)
        points = self.translate(points, translation)

        points = self.rotate(points, rotation_amount)

        translation = (rect.centerx, rect.centery)
        return self.translate(points, translation)

    def translate(self, points, translation):
        result = []
        for point in points:
            result.append((point[0] + translation[0], point[1] + translation[1]))
        return result

    def rotate(self, points, rotation_amount):
        result = []
        angle = rotation_amount * 2 * math.pi
        for point in points:
            x = math.cos(angle) * point[0] - math.sin(angle) * point[1]
            y = math.sin(angle) * point[0] + math.cos(angle) * point[1]
            result.append((x, y))
        return result

    def draw(self, surface, viewport_position, player_timestamp):
        car_state = self.car_state()
        progress = car_state.progress / self.renderer.state.num_laps
        position = self.get_position_for_rendering(player_timestamp)
        self.rect.top = TOP_BORDER + (position - 1) * CAR_WIDTH * (1 + CAR_SPACING)
        self.rect.right = progress * LAP_WIDTH * self.renderer.state.num_laps - viewport_position
        polygon = self.get_polygon(player_timestamp)
        pygame.draw.polygon(surface, self.color, polygon, 0)
        fl = self.renderer.state.fastest_lap()
        if fl is not None and fl.driver_idx == self.car_index:
            img_to_render = self.fl_name_surface
        else:
            img_to_render = self.name_surface

        name_rect = img_to_render.get_rect()
        name_rect.centery = self.rect.centery
        name_rect.left = self.rect.right + 5
        surface.blit(img_to_render, name_rect)

        if car_state.pit_status() != 0:
            pit_img_rect = self.renderer.pit_img.get_rect()
            pit_img_rect.centery = self.rect.centery
            pit_img_rect.left = name_rect.right + 5
            surface.blit(self.renderer.pit_img, pit_img_rect)

        if self.penalties_img is not None:
            penalties_img_rect  = self.penalties_img.get_rect()
            penalties_img_rect.centery = self.rect.centery
            penalties_img_rect.right = self.rect.left - 5
            surface.blit(self.penalties_img, penalties_img_rect)


class Renderer:
    def __init__(self, caption, state):
        pygame.init()
        self.initialize_fonts()

        self.state = state
        self.cars = []

        self.display_surface = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption(caption)

        self.viewport_position = 0

        self.initialize_cars()

        self.prepare_driver_names()

        self.prepare_pit_img()

        self.right_side_space = self.extra_right_space()

    def initialize_fonts(self):
        self.driver_font = pygame.font.Font("font-bold.ttf", CAR_FONT_SIZE)
        self.info_font = pygame.font.Font("font-bold.ttf", INFO_FONT_SIZE)
        self.lap_font = pygame.font.Font("font-bold.ttf", TRACK_FONT_SIZE)

    def initialize_cars(self):
        for i in range(len(self.state.car_states)):
            self.cars.append(Car(i, self))

    def prepare_driver_names(self):
        max_base_name_width = max([car.get_base_name_width() for car in self.cars])
        for car in self.cars:
            car.prepare_name_surfaces(max_base_name_width)

    def prepare_pit_img(self):
        self.pit_img = text.prepare_text("PIT", self.driver_font, (0, 0, 0), (255, 255, 0), height=CAR_WIDTH, border=TEXT_BOX_BORDER)

    def max_name_width(self):
        return max([car.name_surface.get_rect().width for car in self.cars])

    def extra_right_space(self):
        return self.max_name_width() + 20

    def update_viewport(self, session_progress):
        initial_viewport_position = VIEWPORT_INITIAL_X
        final_viewport_position = LAP_WIDTH * self.state.num_laps - WINDOW_WIDTH + max(RIGHT_BORDER, self.right_side_space)
        return initial_viewport_position + session_progress * (final_viewport_position - initial_viewport_position)

    def update(self):
        self.display_surface.fill((160, 160, 160))
        progress = self.state.session_progress
        if progress > 1:
            progress = 1
        self.viewport_position = self.update_viewport(progress)
        self.draw_track(self.display_surface)

        for car in self.cars:
            car.update(self.state.player_timestamp)
        sorted_cars = sorted(self.cars, key=lambda c: -c.get_current_position_for_z_order())
        for car in sorted_cars:
            if car.is_active():
                car.draw(self.display_surface, self.viewport_position, self.state.player_timestamp)

        if self.state.is_safety_car():
            info_text = f"[SC]"
            img = self.info_font.render(info_text, True, (255, 255, 0))
            self.display_surface.blit(img, (5, 5))

    def draw_track(self, surface):
        for i in range(0, self.state.num_laps + 1):
            lap_x = i * LAP_WIDTH - self.viewport_position
            if -LAP_WIDTH < lap_x < WINDOW_WIDTH + LAP_WIDTH:
                pygame.draw.line(surface, (255, 255, 255), (lap_x, 0), (lap_x, WINDOW_HEIGHT), 4)
                if i < self.state.num_laps + 1:
                    lap_text = f"Lap {i+1}"
                    lap_text_img = self.lap_font.render(lap_text, True, (255, 255, 255))
                    self.display_surface.blit(lap_text_img, (lap_x + 10, 5))


