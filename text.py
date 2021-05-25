import pygame


def prepare_text(text, font, fg_color, bg_color=None, width=None, height=None, border=0):
    text_img = font.render(text, True, fg_color)
    if bg_color is None and width is None and height is None:
        return text_img

    if width is None:
        width = text_img.get_rect().width
    if height is None:
        height = text_img.get_rect().height

    text_surf = pygame.Surface((width + 2 * border, height), pygame.SRCALPHA)

    if bg_color is not None:
        text_surf.fill(bg_color)

    rect = text_img.get_rect()
    rect.center = text_surf.get_rect().center
    rect.left = border
    text_surf.blit(text_img, rect)
    return text_surf
