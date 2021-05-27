import pygame.locals
import sys
import state
import render
import video
from session import Session

from render import WINDOW_HEIGHT, WINDOW_WIDTH, FPS, SECONDS_PER_LAP, START_FRAME

VIDEO_OUT="/Users/dneto/dev/raceviewer/video.avi"

SESSION_FILE="/Users/dneto/dev/raceview/raceviewer/F1_2019_14cc77fd5922e307.sqlite3"
# SESSION_FILE="/Users/dneto/dev/raceviewer/F1_2019_e9444ba7f05db735.sqlite3"
NAMES_FILE=None

def run():
    # session.Session("/Users/dneto/dev/raceviewer/F1_2019_e9444ba7f05db735.sqlite3", "/Users/dneto/dev/raceviewer/driver_names.txt")
    session = Session(SESSION_FILE, NAMES_FILE)
    game_state = state.GameState(session, FPS, SECONDS_PER_LAP, START_FRAME)
    renderer = render.Renderer("Race Viewer", game_state)
    video_out = video.VideoWriter(VIDEO_OUT, WINDOW_WIDTH, WINDOW_HEIGHT, FPS)

    clock = pygame.time.Clock()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.locals.QUIT:
                pygame.quit()
                video_out.close()
                sys.exit()

        renderer.update()
        video_out.export_frame(renderer.display_surface)
        pygame.display.update()
        clock.tick(FPS)
        if not game_state.next_frame():
            pygame.quit()
            video_out.close()
            sys.exit()


if __name__ == "__main__":
    run()