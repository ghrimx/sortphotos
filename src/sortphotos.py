#!/usr/bin/env python
# encoding: utf-8

import sys
import os
import shutil
import time
import logging
import logging.config
from uuid import uuid1

import filecmp
from pathlib import Path
from datetime import datetime, timedelta
import re
import locale
from exiftool import ExifTool

from progressbar import ProgressBar, Spinner
from common import MEDIA_EXTENSIONS

# Setting locale to the 'local' value
locale.setlocale(locale.LC_ALL, '')

# init logging
logger = logging.getLogger("sortphotos")
LOG_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR":    logging.ERROR,
    "WARNING":  logging.WARNING,
    "INFO":     logging.INFO,
    "DEBUG":    logging.DEBUG,
}

exiftool_dir = Path("/home/usr2046/Github/sortphotos/src/Image-ExifTool-13.45")
exiftool_path = exiftool_dir.joinpath('exiftool')

# -------- convenience methods -------------

def parse_date_exif(date_string):
    elements = str(date_string).strip().split()
    if len(elements) < 1:
        return None

    date_entries = elements[0].split(':')
    if len(date_entries) == 3 and date_entries[0] > '0000' and '.' not in ''.join(date_entries):
        year = int(date_entries[0])
        month = int(date_entries[1])
        day = int(date_entries[2])
    else:
        return None

    time_zone_adjust = False
    hour = 12
    minute = 0
    second = 0

    if len(elements) > 1:
        time_entries = re.split(r'(\+|-|Z)', elements[1])
        time = time_entries[0].split(':')

        if len(time) == 3:
            hour = int(time[0]); minute = int(time[1]); second = int(time[2].split('.')[0])
        elif len(time) == 2:
            hour = int(time[0]); minute = int(time[1])

        if len(time_entries) > 2:
            time_zone = time_entries[2].split(':')
            if len(time_zone) == 2:
                time_zone_hour = int(time_zone[0])
                time_zone_min = int(time_zone[1])
                if time_entries[1] == '+':
                    time_zone_hour *= -1
                dateadd = timedelta(hours=time_zone_hour, minutes=time_zone_min)
                time_zone_adjust = True

    try:
        date = datetime(year, month, day, hour, minute, second)
    except ValueError:
        return None

    try:
        date.strftime('%Y/%m-%b')
    except ValueError:
        return None

    if time_zone_adjust:
        date += dateadd

    return date


def get_oldest_timestamp(data, additional_groups_to_ignore, additional_tags_to_ignore, print_all_tags=False):
    date_available = False
    oldest_date = datetime.now()
    oldest_keys = []
    src_file = data['SourceFile']
    ignore_groups = ['ICC_Profile'] + additional_groups_to_ignore
    ignore_tags = ['SourceFile', 'XMP:HistoryWhen'] + additional_tags_to_ignore

    for key in data.keys():

        if (key not in ignore_tags) and (key.split(':')[0] not in ignore_groups) and 'GPS' not in key:
            date = data[key]
            if isinstance(date, list):
                date = date[0]
            try:
                exifdate = parse_date_exif(date)
            except Exception:
                exifdate = None
            if exifdate and exifdate < oldest_date:
                date_available = True
                oldest_date = exifdate
                oldest_keys = [key]
            elif exifdate and exifdate == oldest_date:
                oldest_keys.append(key)

    if not date_available:
        oldest_date = None
    return src_file, oldest_date, oldest_keys


def check_for_early_morning_photos(date, day_begins):
    if date.hour < day_begins:
        logger.debug('moving this photo to the previous day for classification purposes (day_begins=' + str(day_begins) + ')')
        date = date - timedelta(hours=date.hour+1)
    return date


_hash_cache = {}

import hashlib

FAST_HASH_SIZE = 65536  # 64 KB

def fast_hash(path, chunk_size=FAST_HASH_SIZE):
    h = hashlib.blake2b(digest_size=16)
    size = os.path.getsize(path)

    with open(path, "rb") as f:
        h.update(f.read(chunk_size))
        if size > chunk_size:
            f.seek(-chunk_size, os.SEEK_END)
            h.update(f.read(chunk_size))

    return h.digest()

def full_hash(path, block_size=1024 * 1024):
    h = hashlib.blake2b(digest_size=32)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(block_size), b""):
            h.update(chunk)
    return h.digest()

def is_duplicate(src, dest):
    if os.path.getsize(src) != os.path.getsize(dest):
        return False

    key = (src, dest)

    if key not in _hash_cache:
        _hash_cache[key] = fast_hash(src), fast_hash(dest)

    if _hash_cache[key][0] != _hash_cache[key][1]:
        return False

    # Only now do the expensive check
    return full_hash(src) == full_hash(dest)

def is_hidden(path):
    p = Path(path)

    if sys.platform == "win32":
        try:
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(p))
            return bool(attrs & 0x2)  # FILE_ATTRIBUTE_HIDDEN
        except Exception:
            return False

    return any(part.startswith('.') for part in p.parts)

def ask_continue(prompt="Continue? [y/N]: "):
    try:
        resp = input(prompt).strip().lower()
    except EOFError:
        return False
    return resp in ("y", "yes")

# Main method

def sortPhotos(src_dir, dest_dir, sort_format, rename_format, recursive=False,
               copy_files=False, test=False, remove_duplicates=True, day_begins=0,
               additional_groups_to_ignore=['File'], additional_tags_to_ignore=[],
               use_only_groups=None, use_only_tags=None, verbose=True, keep_filename=False):

    logger.info("=" * 64)
    logger.info("SORTPHOTOS - PROCESSING...")
    logger.info("=" * 64)

    run_id = uuid1().time
    sys.stdout.write(f'Run ID: {run_id}\n')
    logger.info(f'Run ID: {run_id}')

    mode = "DRY RUN" if test else "🔥 LIVE 🔥"
    action = "copy" if copy_files else "move" 

    if not os.path.exists(src_dir):
        err = 'Source directory does not exist'
        logger.error(err)
        raise Exception(err)

    args = ['-j', '-a', '-G']
    if use_only_tags is not None:
        additional_groups_to_ignore = []
        additional_tags_to_ignore = []
        for t in use_only_tags:
            args += ['-' + t]
    elif use_only_groups is not None:
        additional_groups_to_ignore = []
        for g in use_only_groups:
            args += ['-' + g + ':Time:All']
    else:
        args += ['-time:all']

    if recursive:
        args += ['-r']
    # args += [src_dir]
    

    metadata = []
    bad_files = []
    skipped_files = []
    duplicate_files = []
    unknown_date_files = []

    # Preprocessing with ExifTool
    with Spinner(f"{mode} - Reading EXIF metadata with ExifTool") as spinner:
        with ExifTool(exiftool_path) as exiftool:
            logger.info("Preprocessing with ExifTool (file-by-file, safe mode).")

            if not test:
                time.sleep(2) # for urgent cancel

            files_found = 0
            for root, _, files in os.walk(src_dir):
                for name in files:
                    file_path = os.path.join(root, name)
                    ext = os.path.splitext(name)[1].lower()

                    if Path(file_path).is_file():
                        files_found += 1
                        spinner.update(f"Processed files: {files_found}")

                    if ext not in MEDIA_EXTENSIONS:
                        skipped_files.append(file_path)
                        logger.debug(f'⚠️ Invalid file extension. file:{file_path}')
                        continue

                    try:
                        md = exiftool.get_metadata(*args, file_path)
                        if not md:
                            bad_files.append(file_path)
                            logger.error(f'⚠️ Fail to get metadata. file:{file_path}')
                            continue
                        metadata.extend(md)
                    except Exception:
                        bad_files.append(file_path)
                        logger.error(f'⚠️ Fail to get metadata. file:{file_path}') 


    if not ask_continue():
        logger.info("Aborted by user")
        logger.info("=" * 64)
        sys.exit(1)

    title = "copying" if copy_files else "moving"
    progress = ProgressBar(len(metadata) - 1, title=f"Sorting photos ({title})")

    # Actions
    cnt = 0
    for idx, data in enumerate(metadata):
        src_file, date, keys = get_oldest_timestamp(data, additional_groups_to_ignore, additional_tags_to_ignore)
        src_file.encode('utf-8')

        if test:
            m = '(DRY RUN - no files are being moved/copied)'
        else:
            m= ""
        logger.debug(f"[{idx+1}/{len(metadata)}] {m}")
        logger.debug('Source: ' + src_file)

        # if no valid date or hidden -> log
        if not date or is_hidden(src_file):
            unknown_date_files.append(src_file)
            continue

        logger.debug('Date/Time: ' + str(date))
        logger.debug('Corresponding Tags: ' + ', '.join(keys))

        date = check_for_early_morning_photos(date, day_begins)
        dir_structure = date.strftime(sort_format)
        dirs = dir_structure.split('/')
        dest_file = dest_dir
        for thedir in dirs:
            dest_file = os.path.join(dest_file, thedir)
            if not test and not os.path.exists(dest_file):
                os.makedirs(dest_file)

        filename = os.path.basename(src_file)
        if rename_format is not None and date is not None:
            _, ext = os.path.splitext(filename)
            filename = date.strftime(rename_format) + ext.lower()

        dest_file = os.path.join(dest_file, filename)
        root, ext = os.path.splitext(dest_file)

        name = 'Destination '
        name += '(copy): ' if copy_files else '(move): '
        logger.debug(name + dest_file)

        # Duplicate detection
        append = 1
        file_is_identical = False
        while os.path.isfile(dest_file):

            logger.debug(f'src_file: {src_file}')
            logger.debug(f'dest_file: {dest_file}')

            if remove_duplicates and is_duplicate(src_file, dest_file):
                file_is_identical = True
                logger.debug("⚠️ Identical file already exists. Duplicate will be ignored.")
                break

            # Filename collision -> generate new name
            if keep_filename:
                orig = os.path.splitext(os.path.basename(src_file))[0]
                dest_file = f"{root}_{orig}_{append}{ext}"
            else:
                dest_file = f"{root}_{append}{ext}"

            append += 1
            logger.debug("⚠️ Same name already exists...renaming to: %s", dest_file)

        if file_is_identical:
            duplicate_files.append(src_file)
            continue

        if not test:
            if copy_files:
                shutil.copy2(src_file, dest_file)
            else:
                shutil.move(src_file, dest_file)
        
        cnt += 1

        progress.update(idx)
        # percent_complete(step=cnt, total_steps=len(metadata) - 1, title=f"{title} ({mode})")
        # print()

    progress.finish()

    logger.info("")
    logger.info("=" * 64)
    logger.info("SORTPHOTOS - RUN SUMMARY")
    logger.info("=" * 64)

    logger.info(f"Mode                            : {mode}")
    logger.info(f"Action                          : {action}")
    logger.info(f"Source files detected           : {files_found}")
    logger.info(f"Source                          : {src_dir}")
    logger.info(f"Destination                     : {dest_dir}")
    logger.info("")

    logger.info("Actions")
    logger.info("-" * 63)
    logger.info(f"Moved/Copied          : {cnt}")
    logger.info(f"Skipped               : {len(skipped_files) + len(bad_files) + len(unknown_date_files)}")
    logger.info(f"Duplicates ignored    : {len(duplicate_files)}")
    logger.info("")

    logger.info("Integrity")
    logger.info("-" * 63)
    logger.info(f"Bad / unreadable files      : {len(bad_files)}")
    logger.info(f"Unknown date/ hidden files  : {len(unknown_date_files)}")
    logger.info("")

    files_affected = cnt
    files_untouched = files_found - files_affected

    logger.info("Result")
    logger.info("-" * 63)
    logger.info(f"Files affected        : {files_affected}")
    logger.info(f"Files untouched       : {files_untouched}")

    logger.info("")

    # Log
    logger.info("=" * 64)
    logger.info("SORTPHOTOS - LOG")
    logger.info("=" * 64)

    if bad_files:
        logger.info(f"{len(bad_files)} bad/unreadable files:")
        logger.info("-" * 63)
        for bf in bad_files:
            logger.info(bf)
    
        logger.info("")

    if skipped_files:
        logger.info(f"{len(skipped_files)} files skipped:")
        logger.info("-" * 63)
        for sf in skipped_files:
            logger.info(sf)
    
        logger.info("")

    if unknown_date_files:
        logger.info(f"{len(unknown_date_files)} unknown date or hidden files:")
        logger.info("-" * 63)
        for uf in unknown_date_files:
            logger.info(uf)
    
        logger.info("")

    if duplicate_files:
        logger.info(f"{len(duplicate_files)} duplicate files:")
        logger.info("-" * 63)
        for df in duplicate_files:
            logger.info(df)

    logger.info("=" * 64)


def main():
    import argparse
    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter,
                                     description='Sort files (primarily photos and videos) into folders by date\nusing EXIF and other metadata')
    parser.add_argument('src_dir', type=str, help='source directory')
    parser.add_argument('dest_dir', type=str, help='destination directory')
    parser.add_argument('-r', '--recursive', action='store_true', help='search src_dir recursively')
    parser.add_argument('-c', '--copy', action='store_true', help='copy files instead of move')
    parser.add_argument('-s', '--silent', action='store_true', help='don\'t display parsing details.')
    parser.add_argument('-t', '--test', action='store_true', help='run a test. files will not be moved/copied\ninstead you will just see a list of what would happen')
    parser.add_argument('--sort', type=str, default='%Y/%m-%b',
                        help="choose destination folder structure using datetime format")
    parser.add_argument('--rename', type=str, default=None,
                        help="rename file using format codes. default is None (original filename)")
    parser.add_argument('--keep-filename', action='store_true', default=False,
                        help='In case of duplicated output filenames append original file name and number')
    parser.add_argument('--keep-duplicates', action='store_true',
                        help='If file is a duplicate keep it anyway (after renaming).')
    parser.add_argument('--day-begins', type=int, default=0, help='hour of day that new day begins (0-23)')
    parser.add_argument('--ignore-groups', type=str, nargs='+', default=[], help='groups to ignore')
    parser.add_argument('--ignore-tags', type=str, nargs='+', default=[], help='tags to ignore')
    parser.add_argument('--use-only-groups', type=str, nargs='+', default=None, help='restrict groups')
    parser.add_argument('--use-only-tags', type=str, nargs='+', default=None, help='restrict tags')
    parser.add_argument("--log-level",
                        default="INFO",
                        choices=LOG_LEVELS.keys(),
                        help="Set logging level (default: INFO)")

    parser.add_argument("--quiet",
                        action="store_true",
                        help="Suppress non-error output (sets log level to ERROR)")

    args = parser.parse_args()

    if args.quiet:
        log_level = logging.ERROR
    else:
        log_level = LOG_LEVELS[args.log_level]

    logging.basicConfig(filename='sortphotos.log',
                        level=log_level,
                        format="%(asctime)s | %(levelname)-8s | %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S"
                        )

    logger.info("*" * 64)
    logger.info("")
    logger.info(" " * 27 + "SORTPHOTOS")
    logger.info("")
    logger.info("*" * 64)

    sortPhotos(args.src_dir, args.dest_dir, args.sort, args.rename, args.recursive,
               args.copy, args.test, not args.keep_duplicates, args.day_begins,
               args.ignore_groups, args.ignore_tags, args.use_only_groups,
               args.use_only_tags, not args.silent, args.keep_filename)

if __name__ == '__main__':
    main()
