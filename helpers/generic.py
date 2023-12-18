from helpers.paths import DATA_DIR


def get_instance_number():
    i = 0
    while True:
        name = f"instance_{i}"
        if not (DATA_DIR / name).exists():
            return i
        i += 1


INSTANCE_NO = get_instance_number()


def camelize(string):
    # WIP
    return string.replace(" ", "_").lower().replace("representative", "rep")
