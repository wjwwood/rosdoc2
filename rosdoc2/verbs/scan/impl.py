# Copyright 2024 R. Kent James <kent@caspia.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import multiprocessing as mp
import os
import signal
import sys
import threading
import time

from catkin_pkg.packages import find_packages_allowing_duplicates
from rosdoc2.verbs.build.impl import main_impl as build_main_impl
from rosdoc2.verbs.build.impl import prepare_arguments as build_prepare_arguments

logging.basicConfig(
    format='[%(name)s] [%(levelname)s] %(message)s', level=logging.INFO)
logger = logging.getLogger('rosdoc2')
logger_scan = logging.getLogger('rosdoc2.scan')

goptions = None
# Setting the MAX_PACKAGES to a smaller value may be useful in debugging
# this module, to reduce run time or isolate sections that cause hangs.
MAX_PACKAGES = 10000
WATCHDOG_TIMEOUT = 15 * 60  # Seconds


def main(options):
    """Execute the program, catching errors."""
    try:
        return main_impl(options)
    except Exception as e:  # noqa: B902
        if options.debug:
            raise
        else:
            sys.exit(str(e))


class Struct:
    """Wrap argparse options to allow copies."""

    def __init__(self, **entries):
        """Create a dictionary from option entries."""
        self.__dict__.update(entries)


def prepare_arguments(parser):
    """Add command-line arguments to the argparse object."""
    # Wrap the builder arguments to include their choices.
    build_prepare_arguments(parser)

    # Additional options for scan
    parser.add_argument(
        '--timeout',
        '-t',
        default=WATCHDOG_TIMEOUT,
        help='maximum time in seconds allowed per package',
    )
    parser.add_argument(
        '--max-packages',
        '-m',
        default=MAX_PACKAGES,
        help='maximum number of packages to process'
    )
    parser.add_argument(
        '--subprocesses',
        '-s',
        default=None,
        help='number of subprocesses to use, defaults to os.cpu_count()'
    )
    return parser


def main_impl(options):
    """Execute the program."""
    global goptions
    goptions = options

    if options.install_directory is not None:
        logger.warn(
            'The --install-directory option (-i) is unused and will be removed in a future version')

    # Locate the packages to document.
    found_packages = find_packages_allowing_duplicates(options.package_path)
    packages = list(found_packages.values())
    if len(packages) == 0:
        logger_scan.error(f'No packages found in subdirectories of {options.package_path}')
        exit(1)
    max_packages = int(options.max_packages)
    subprocesses = int(options.subprocesses) if options.subprocesses is not None else None
    if len(packages) > max_packages:
        packages = packages[0:max_packages]
    packages_total = len(packages)
    packages_done = 0
    logger_scan.info(f'Processing {packages_total} packages')
    failed_packages = []
    for package in packages:
        logger_scan.info(f'Adding {package.name} for processing')

    pool = mp.Pool(maxtasksperchild=1, processes=subprocesses)
    pool_results = pool.imap_unordered(package_impl, packages)
    while True:
        try:
            (package, returns, message) = pool_results.next()
            packages_done += 1
            if returns != 0:
                logger_scan.warning(f'{package.name} ({packages_done}/{packages_total})'
                                    f' returned {returns}: {message}')
                failed_packages.append((package, returns, message))
            else:
                logger_scan.info(
                    f'{package.name} successful ({packages_done}/{packages_total})')
        except StopIteration:
            break
        except BaseException as e:  # noqa: B902
            logger_scan.error(f'Unexpected error in scan: {type(e).__name__ + " " + str(e)}')
            break
    logger_scan.info('Finished')
    # I'd prefer close() then join() but that seems to sometimes hang.
    pool.terminate()

    logger_scan.info('scan complete')
    if len(failed_packages) > 0:
        print(f'{len(failed_packages)} packages failed:')
        for failed in failed_packages:
            (package, returns, message) = failed
            print(f'{package.name}: retval={returns}: {message}')
    else:
        print('All packages succeeded')


def _clocktime():
    return time.strftime('%H:%M:%S')


def package_impl(package):
    """Execute for a single function."""
    global goptions
    options = Struct(**goptions.__dict__)
    package_path = os.path.dirname(package.filename)
    options.package_path = package_path
    return_value = 100
    message = 'Unknown error'
    start = time.time()
    had_timeout = threading.Event()

    def watchdog():
        """Kill the process after a timeout."""
        time.sleep(float(options.timeout))
        had_timeout.set()
        os.kill(os.getpid(), signal.SIGINT)
    threading.Thread(target=watchdog, daemon=True).start()

    # Generate the doc build directory.
    os.makedirs(options.doc_build_directory, exist_ok=True)

    print(f'{_clocktime()} Begin processing {package.name}', flush=True)
    # remap output
    outfile = open(os.path.join(options.doc_build_directory, f'{package.name}.txt'), 'w')
    old_stdout = sys.stdout
    old_stderr = sys.stderr
    sys.stdout = outfile
    sys.stderr = outfile
    logging.basicConfig(
        format='%(asctime)s [%(name)s] [%(levelname)s] %(message)s',
        level=logging.INFO, stream=outfile, force=True)
    logger = logging.getLogger('rosdoc2')
    logger.info(f'Processing package build at {package_path}')

    try:
        # run rosdoc2 for the package
        build_main_impl(options)
        return_value = 0
        message = 'OK'
    except RuntimeError as e:
        return_value = 1
        message = type(e).__name__ + ' ' + str(e)
    except KeyboardInterrupt as e:
        return_value = 2
        if had_timeout.is_set():
            e = TimeoutError(f'runtime {"{:.3f}".format(time.time() - start)} seconds')
        message = type(e).__name__ + ' ' + str(e)
    except BaseException as e:  # noqa: B902
        return_value = 3
        message = type(e).__name__ + ' ' + str(e)
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        elapsed_time = '{:.3f}'.format(time.time() - start)
        if return_value != 0:
            print(f'{_clocktime()} Package at {package_path} failed {return_value}: {message}',
                  flush=True)
            logger.error(f'Package at {package_path} failed {return_value}: {message}')
        else:
            print(f'{_clocktime()} Package {package.name} succeeded '
                  f'in {elapsed_time} seconds', flush=True)
            logger.info(f'Completed rosdoc2 build for {package_path} '
                        f'in {elapsed_time} seconds')
        if not outfile.closed:
            outfile.close()
        return (package, return_value, message)
