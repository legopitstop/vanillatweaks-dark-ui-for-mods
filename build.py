import json
import os
import modrinth
import requests
import logging
import zipfile
import io
import fnmatch
import shutil
import sys
from PIL import Image, ImageColor  # Use pillow-simd

logging.basicConfig(
    format="[%(asctime)s] [%(name)s/%(levelname)s]: %(message)s",
    datefmt="%I:%M:%S",
    handlers=[
        logging.FileHandler("latest.log", mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
    level=logging.INFO,
)

try:
    import dotenv
    dotenv.load_dotenv()
except ImportError:
    ...
except Exception:
    logging.warn("Failed to load .env file.")


def get_file(mod) -> bytes | None:
    """Returns the mod's file"""
    projectID = mod["projectID"]
    fileID = mod["fileID"]
    match mod["type"]:
        case "modrinth":
            project = modrinth.Projects.ModrinthProject(projectID)
            version = project.getVersion(fileID)
            primaryFile = version.getFiles()[0]
            url = version.getDownload(primaryFile)
            logging.info("Fetching '%s'", url)
            res = requests.get(url)
            if res.status_code != 200:
                logging.warn(
                    "InvalidRequest - '%s' %s %s", url, res.status_code, res.content
                )
                return None
            return res.content

        case _:
            logging.warn("InvalidModType - %s", mod)
            return None


def get_modpack_files(modpack) -> list[bytes]:
    """Return a list of mod files"""
    projectID = modpack["projectID"]
    fileID = modpack["fileID"]
    match modpack["type"]:
        case "modrinth":
            project = modrinth.Projects.ModrinthProject(projectID)
            version = project.getVersion(fileID)
            primaryFile = version.getFiles()[0]
            url = version.getDownload(primaryFile)
            logging.info("Fetching '%s'", url)
            res = requests.get(url)
            if res.status_code != 200:
                logging.warn(
                    "InvalidRequest - '%s' %s %s", url, res.status_code, res.content
                )
                return None

            mods = []
            with zipfile.ZipFile(io.BytesIO(res.content)) as zip:
                with zip.open("modrinth.index.json") as fd:
                    index = json.load(fd)
                    for file in index["files"]:
                        url = file["downloads"][0]
                        logging.info("Fetching '%s'", url)
                        res = requests.get(url)
                        if res.status_code != 200:
                            logging.warn(
                                "InvalidRequest - %s %s", res.status_code, res.content
                            )
                            return None
                        mods.append(res.content)
            return mods
        case _:
            logging.warn("InvalidModPackType - %s", modpack)
            return None


def convert_image(colors, file):
    """Convert pixels"""
    img = Image.open(file)
    img = img.convert("RGBA")
    data = img.load()
    edited = False
    # TODO: Could this use numpy/be ran on the GPU?

    for y in range(img.size[1]):
        for x in range(img.size[0]):
            for light, dark in colors.items():
                if data[x, y] == light:
                    data[x, y] = dark
                    edited = True
    return img if edited else None


def main():
    modpackstxt = []
    modstxt = []

    # Load mcmeta
    with open('src/pack.mcmeta') as fd:
        mcmeta = json.load(fd)

    # Setup dist from src
    shutil.copytree("src", "dist", dirs_exist_ok=True)

    with open("config.json") as fd:
        config = json.load(fd)

    modpacks = config["modpacks"]
    mods = config["mods"]

    # Parse colors
    colors = {}
    for light, dark in config["colors"].items():
        colors[ImageColor.getcolor(light, "RGBA")] = ImageColor.getcolor(dark, "RGBA")

    files = []

    # Get mod modpack files
    for modpack in modpacks:
        pmods = get_modpack_files(modpack)
        if not pmods:
            continue
        modpackstxt.append(
            "- (modpack) "
            + modpack["name" if "name" in modpack else modpack["projectID"]]
        )
        files.extend(pmods)

    # Get mod files.
    for mod in mods:
        file = get_file(mod)
        if not file:
            continue
        modstxt.append("- (mod) " + mod["name" if "name" in mod else mod["projectID"]])
        files.append(file)

    # Load files.
    for file in files:
        buf = io.BytesIO(file)
        with zipfile.ZipFile(buf) as jar:
            # logging.info(mod)
            for filename in jar.namelist():
                if fnmatch.fnmatch(
                    filename, "assets/**/*.png"
                ):  # TODO: path should contain "gui" or "ui"
                    if "gui" not in filename or "ui" not in filename:
                        continue
                    dmp = os.path.join("dist", filename)
                    file = jar.open(filename)
                    img = convert_image(colors, file)
                    if not img:
                        continue

                    # Skip if file exists
                    if os.path.isfile(dmp):
                        logging.info("- (skipped) 'dist/%s'", filename)
                        continue

                    # Make dir
                    os.makedirs(os.path.dirname(dmp), exist_ok=True)

                    # Save img
                    img.save(dmp, format="PNG")

                    logging.info("- (added) 'dist/%s'", filename)

    with open("dist/contents.txt", "w") as fd:
        contents = (
            "Modpacks:\n"
            + "\n".join(modpackstxt)
            + "\nMods:\n"
            + "\n".join(modstxt)
            + "\n"
        )
        fd.write(contents)

    # Archive dist
    version = '.'.join([str(x) for x in mcmeta['pack']['version']])
    shutil.make_archive('libs/Resource Pack-'+version, 'zip', 'dist')

if __name__ == "__main__":
    main()
