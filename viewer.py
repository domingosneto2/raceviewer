import pygame.locals
import sys
import state
import render
import video
from render import WINDOW_HEIGHT, WINDOW_WIDTH, FPS, SECONDS_PER_LAP, START_FRAME


def run():
    game_state = state.GameState(FPS, SECONDS_PER_LAP, START_FRAME)
    renderer = render.Renderer("Race Viewer", game_state)
    video_out = video.VideoWriter("/Users/dneto/dev/raceviewer/video.avi", WINDOW_WIDTH, WINDOW_HEIGHT, FPS)

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