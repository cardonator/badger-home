"""A path-independent app for testing the store's writable launch slot."""

screen.font = font.nope
presses = 0
print("STORE_PROBE: launched from writable slot or normal app directory")


def update():
    global presses
    if badge.pressed(BUTTON_SELECT):
        presses += 1
        print("STORE_PROBE: select", presses)

    screen.pen = color.rgb(13, 17, 23)
    screen.rectangle(screen.clip)
    screen.pen = color.rgb(95, 237, 131)
    screen.text("Store Probe", 10, 14)
    screen.pen = color.rgb(245, 245, 245)
    screen.text("App is running", 10, 40)
    screen.text("Select: %s" % presses, 10, 62)
    screen.pen = color.rgb(160, 174, 190)
    screen.text("Home: badge menu", 10, 96)


run(update)
