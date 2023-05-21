import glassy
import glassy.utils as gtil
import io
import json
import ntpath
import os
import os.path as ntpath
import random
import re
import shutil
import time
import traceback
from zipfile import ZipFile

import requests

anouncement_handler = gtil.EventRegistery()

_start_time: float = 0.0

# dependency_matcher = re.compile(r'(^\??)\s*([\w-_]+)\s*([><=]*)\s*([\d.]*)')
title_matcher = re.compile(r'[\w_-]+')
version_matcher = re.compile(r'(\d+)\.(\d+)\.(\d+)')
version_matcher_flex = re.compile(r'(\d+)\.(\d+)(?:\.(\d+))?')
op_matcher = re.compile(r'[=<>]{1,2}')
factorio_modfile_name_pattren = re.compile(r'(\w*[a-z_-]+)(\d+\.\d+\.\d+)\.zip')
url_id_extractor = re.compile(r'mod/([\w_-]+)')
DEP_OPTIONAL = 1
maximum_announcements_level = 10

processing_url: str = ''
processing_id: str = ''
processing_args: dict = {}
processing_version: gtil.VersionInfo|None = None

mod_file_contents: bytes = bytes()

cached_info: dict[str, gtil.VersionInfo] = {}

factorio_version = gtil.VersionInfo('1.1.0')

factorio_appdata_folder: str = r'C:\Program Files (x86)\Factorio'

_mod_request_rand_value = '021789155387211379'

__folder__ = gtil.parent_path(__file__)
def to_local_path(p: str) -> str:
    return ntpath.join(__folder__, p)

config_path = to_local_path('config.json')

temp_mods_path = to_local_path('.temps')
processed_mods_path = to_local_path('mods')
cache_file_path = to_local_path('cache.bin')

if not ntpath.exists(temp_mods_path) or not ntpath.isdir(temp_mods_path):
    os.mkdir(temp_mods_path)
if not ntpath.exists(processed_mods_path) or not ntpath.isdir(processed_mods_path):
    os.mkdir(processed_mods_path)

def mod_temp_extraction_path(mod_id = None) -> str:
    if mod_id is None: mod_id = processing_id
    return ntpath.join(processed_mods_path, f'{mod_id}')
def mod_zip_path(name: str, version: gtil.VersionInfo) -> str:
    return ntpath.join(processed_mods_path, f'{name}_{version}.zip')

def announce_title(t: str):
    lt = max(len(i) for i in t.splitlines())
    print('-' * lt)
    print(t)
    print('-' * lt)

def announce(*args, level: int = 0):
    """:param args: what to print
    :param level: printing level, higher levels are for more technical stuff
    :return:
    """
    if level > maximum_announcements_level:
        return
    print('>>>', *args)
    anouncement_handler(*args, level=level)

def breakup_modfile_path(path: str):
    return gtil.parent_path(path), breakup_modfile_name(gtil.filename(path))
def breakup_modfile_name(name: str):
    x = version_matcher.search(name)
    if x is not None:
        return name[:x.span()[0] - 1], gtil.VersionInfo(x[0])
    return None

def extract_id_from_url(url: str) -> str | None:
    x = url_id_extractor.search(url)
    print(url, x)
    if x is None:
        return None
    return x[1]

class ModDependency(gtil.VersionRequirment):
    
    @property
    def optional(self):
        return self.is_optional
    @property
    def mod_id(self):
        return self.m_id
    
    def __init__(self, *, m_id: str, optional: bool, op: int = 0, version: str = '0.0.0'):
        super().__init__(op=op, version=version)
        self.m_id: str = m_id
        self.is_optional: bool = optional

    def __str__(self):
        return f'<ModDependency, optional={self.optional}, op={gtil.op_sympol(self.oprator)}, id={self.mod_id}, version={self.version}>'


class FactorioModInfo:
    name: str = ''
    description: str = ''
    version: gtil.VersionInfo = None
    title: str = ''
    author: str = ''
    email: str = ''
    homepage: str = ''
    contact: str = ''
    factorio_version: str = ''
    dependencies: list[ModDependency] = list
 
    __attrs__ = [
        'name',
        'description',
        'title',
        'author',
        'email',
        'homepage',
        'contact',
        'factorio_version',
        'dependencies'
    ]
    
    
    str_wraper = [i + '=' + '"%s"' for i in __attrs__]
    str_wraper = gtil.join(str_wraper, ', ')
    
    # __slots__ = __attrs__
 
    def __init__(self, *,
                 name: str = '',
                 description: str = '',
                 version: gtil.VersionInfo | str | None = None,
                 title: str = '',
                 author: str = '',
                 email: str = '',
                 homepage: str = '',
                 contact: str = '',
                 factorio_version: str = '',
                 dependencies: list[ModDependency] = None):
        if dependencies is None:
            dependencies = []
        if version is None:
            version = gtil.VersionInfo('0.0.0')
        elif version is str:
            version = gtil.VersionInfo(version)
        self.name = name
        self.description = description
        self.version = version
        self.title = title
        self.author = author
        self.email = email
        self.homepage = homepage
        self.contact = contact
        self.factorio_version = factorio_version
        self.dependencies = dependencies
    
    
    
    def __str__(self):
        
        return f'<FactorioModInfo {self.str_wraper % tuple(getattr(self, i) for i in self.__attrs__)}>'

class FactorioMod(glassy.GlassyObj):
    info: FactorioModInfo = None
    path: str = ''
    
    
    def __init__(self):
        pass
        
        
processing_info: FactorioModInfo|None = None

def print_error(e: Exception):
    t = str(e)
    announce('-' * 64)
    announce(t)
    x = traceback.extract_stack()
    announce(x[:-1])
    announce('-' * 64)

def validate_short_version(v: str) -> str:
    p = v.split('.')
    if len(p) == 2:
        v = v.strip().strip('.') + '.0'
    return v

def parse_dependency(dep: str):
    dep = dep.strip()
    optional = '?' in dep
    op_m = op_matcher.search(dep)
    title_m = title_matcher.search(dep)
    if title_m is None:
        raise ValueError(f'No mod id in dep {dep}')
    
    ver_t = None
    op: int = 0
    
    if op_m is not None:
        op = gtil.sympol_to_op(op_m[0])
        ver_t = version_matcher_flex.search(dep)
        if ver_t is None:
            raise ValueError(f'No version found in dep {dep}')
        
    
    return  ModDependency(m_id=title_m[0], optional=optional, op=op,version=validate_short_version(ver_t[0]))


def parse_dependencies(deps: list[str]):
    results: list[ModDependency] = []
    
    for i in deps:
        print(i)
        results.append(parse_dependency(i))
    
    return results

def build_info_file(data: dict[str]) -> FactorioModInfo:
    return FactorioModInfo(
        # name=data.get('name', ''),
        name=processing_id,
        # description=data.get('description', ''),
        # version=data.get('version', ''),
        version=processing_version,
        # title=data.get('title', ''),
        # author=data.get('author', ''),
        # email=data.get('email', ''),
        # homepage=data.get('homepage', ''),
        # contact=data.get('contact', ''),
        factorio_version=data.get('factorio_version', ''),
        dependencies=parse_dependencies(data.get('dependencies', [])),
    )


def completed():
    announce(f'[ [ [ COMPLETED DOWNLOADING IN {time.time() - _start_time}s ] ] ]')


def _process_mod_info(text: str):
    try:
        js_data = json.JSONDecoder().decode(text)
    except TypeError as e:
        print_error(e)
        return None
    except Exception as e:
        print_error(e)
        return None
    try:
        b = build_info_file(js_data)
        print('b found of ', b)
        return b
    except Exception as e:
        print_error(e)
        return None

def load_mod_info(at: str) -> FactorioModInfo | None:
    if not ntpath.exists(at):
        raise FileNotFoundError(f'No info file at "{at}"')
    elif not ntpath.isfile(at):
        raise gtil.InvalidPathError(f'"{at}" isn\'t a file')
    
    try:
        with open(at, 'r') as file:
            text = file.read()
    except OSError as e:
        print_error(e)
        return None
    return _process_mod_info(text)

def save_cache_to_json():
    path = to_local_path('cache.json')
    with open(path, 'w') as f:
        json.dump(cached_info, f, cls=glassy.JSONEncoder, indent=4)


def update_cache():
    global cached_info
    mods_folder = ntpath.join(factorio_appdata_folder, 'mods')
    
    zip_files = [(i.path, breakup_modfile_path(i.path)) for i in os.scandir(mods_folder) if i.is_file() and gtil.extension(i.path).lower() == 'zip']
    for i, j in zip_files:
        if j[1] is None:
            announce(f'Invalid mod filename at path {i}', level=3)
            continue
        br = j[1]
        if br[0] not in cached_info or cached_info[br[0]] < br[1]:
            cached_info[br[0]] = br[1]
        else:
            announce(f'Duplicate mod filename {br[0]}: current version: {cached_info[br[0]]}, duplicate version: {br[1]}', level=3)
            continue
            
        
    
    cached_info['base'] = factorio_version

def dependency_met(r: ModDependency):
    return r.mod_id in cached_info and r.matches_requiremnts(cached_info[r.mod_id])
def dependencies_met(r: list[ModDependency]):
    for i in gtil.irange(r):
        yield i, dependency_met(r[i])

def build_mod(at: str):
    # info_path = ntpath.join(at, 'info.json')
    # info = load_mod_info(info_path)
    # valid_info: bool = info is not None
    # if not valid_info:
    #     announce(f'no valid mod info found at {info_path}')
    #     info = FactorioModInfo(name=str(processing_id), version='0.0.0')
    #
    # announce(f'fetched mod info {info}')
    
    result_path = mod_zip_path(processing_id, processing_version)
    with open(result_path, 'wb') as file:
        file.write(mod_file_contents)
        announce(f'saved mod at {result_path}')

def is_mod_folder(path: str) -> bool:
    info_path = ntpath.join(path, 'info.json')
    return ntpath.exists(info_path) and ntpath.isfile(info_path)


def _start_processing_mod_info(info: str):
    global processing_version, mod_file_contents
    try:
        js_data: dict[str] = json.JSONDecoder().decode(info)
        target_release = js_data['releases'][-1]
    except Exception as e:
        print_error(e)
        announce('Failed to parse the mod\'s info json')
        return
    processing_version = gtil.VersionInfo(target_release['version'])
    announce(f'downloading "{processing_id}" version {processing_version}...')
    x = _request_mod()
    
    if x.ok:
        announce(f'Done downloading "{processing_id}" in {x.elapsed}')
        mod_file_contents = x.content
    else:
        announce(f'Failed to download "{processing_id}" with reason: {x.reason}')
    
    
    
    

def _start_processing_mod():
    global mod_file_contents
    extraction_path = mod_temp_extraction_path()
    announce(f'Extracting "{processing_id}" to {extraction_path}')
    zip_file : ZipFile|None = None
    try:
        zip_file = ZipFile(io.BytesIO(mod_file_contents), 'r')
        zip_file.extractall(extraction_path)
    except Exception as e:
        print_error(e)
        file_bin_drop_path = ntpath.join(gtil.parent_path(extraction_path), processing_id + ".bin")
        announce(f'Couldn\'t extract "{processing_id}" to {file_bin_drop_path}; saving to file')
        with open(ntpath.join(file_bin_drop_path), 'wb') as f:
            f.write(mod_file_contents)
        return
    
    
    ps : list[os.DirEntry] = [i for i in os.scandir(extraction_path)]
    base_mod_folder: str | None = None
    
    for i in ps:
        if i.is_dir() and is_mod_folder(i.path):
            base_mod_folder = i.path
            break
    if base_mod_folder is None:
        announce(f'No mod base folder found for mod({processing_id}) at extraction folder {extraction_path}')
        return
    else:
        announce(f'found mod base folder {base_mod_folder}')
    build_mod(base_mod_folder)
    completed()

def _mods_cleanup():
    extraction_path = mod_temp_extraction_path()
    if not ntpath.exists(extraction_path):
        return
    shutil.rmtree(extraction_path)

def process_mod(info: str):
    _start_processing_mod_info(info)
    _start_processing_mod()
    _mods_cleanup()

def _get_request_url(version: gtil.VersionInfo):
    return f'https://factorio-launcher-mods.storage.googleapis.com/{processing_id}/{version}.zip'

def _get_info_request_url():
    global _mod_request_rand_value
    _mod_request_rand_value = str(random.random).replace('.', '')
    return f'https://re146.dev/factorio/mods/modinfo?rand={_mod_request_rand_value}&id={processing_id}'

def _get_info_request_data():
    return dict(rand=_mod_request_rand_value,id=processing_id)

def _request_mod_info() -> requests.Response:
    return requests.get(
        _get_info_request_url(),
        data=_get_info_request_data()
    )
    
def _request_mod() -> requests.Response:
    timeout = 15
    current_key: str = ''
    
    def exists(k_type = None, key: str = current_key):
        return key in processing_args and (k_type is None or isinstance(processing_args[key], k_type))
    
    def announce_invalid_arg(massege: str, key: str = current_key):
        announce(f'Error in argument "{key}": {massege}')

    current_key = 'timeout'
    if exists():
        if exists((int, float)):
            timeout = processing_args['timeout']
            if timeout <= 0.1:
                timeout = 0.2
                announce_invalid_arg('timeout', 'must be positive and over 0.1')
        else:
            announce_invalid_arg('timeout', 'must be a numper')
        
    return requests.get(
        _get_request_url(processing_version),
        timeout=timeout
    )

def download_and_process_mod(url: str, *, args: dict[str] = None):
    """called by main to start downloading"""
    global _start_time
    _start_time = time.time()
    args = gtil.default(args)
    
    global processing_url, processing_id, processing_args
    processing_url = url
    processing_args = args
    mid = extract_id_from_url(url)
    if mid is None:
        announce(f'Invalid url (Can\'t find the mod\'s id): "{url}"')
        return
    processing_id = mid.strip()
    announce(f'Requesting "{processing_id}"...')
    x = _request_mod_info()
    announce(f'Completed Request (INFO) "{processing_id}" in {x.elapsed}', level=6)
    if x.ok:
        announce(f'Processing the mod "{processing_id}"')
        process_mod(x.content.decode('utf-8'))
    else:
        announce(f'Failed to request [INFO] "{processing_id}" with reason: {x.reason}')


def load_data():
    """called at start to load the config from"""
    global  factorio_appdata_folder, factorio_version
    def dump_defaults():
        with open(config_path, 'w') as jf:
            json.dump({
                "factorio_data_dir": factorio_appdata_folder,
                "factorio_version": factorio_version.version
            }, jf, indent=4)
    if not ntpath.exists(config_path):
        dump_defaults()
        return
    with open(config_path, 'r') as f:
        try:
            data = json.load(f)
        except Exception as e:
            print_error(Exception("failed to parse config file, overwriting config to the default one"))
            print_error(e)
            dump_defaults()
            return
    if not isinstance(data, dict):
        print_error(ValueError("invalid config json format (base data should be an object)"))
        return
    factorio_folder = data.get("factorio_data_dir", "")
    if not factorio_folder or not ntpath.isdir(factorio_folder):
        print_error(ValueError("'factorio_data_dir' key in config file is invalid or not a directory"))
    else:
        factorio_appdata_folder = factorio_folder
    if not "factorio_version" in data:
        print_error(ValueError("there is no 'factorio_version' key in the config file"))
    else:
        try:
            new_current_factorio_version = gtil.VersionInfo(data["factorio_version"])
        except Exception as e:
            print_error(Exception("invalid 'factorio_version' in confing file with error:"))
            print_error(e)
            new_current_factorio_version = None
        if new_current_factorio_version is not None:
            factorio_version = new_current_factorio_version
    

def check_for_errors():
    has_errors = False
    if not ntpath.exists(factorio_appdata_folder):
        print_error(FileExistsError(f"factorio data folder does not exist: '{factorio_appdata_folder}'"))
        has_errors = True
    elif not ntpath.isdir(factorio_appdata_folder):
        print_error(FileExistsError(f"factorio data folder is not a directory: '{factorio_appdata_folder}'"))
        has_errors = True
    if factorio_version is None:
        print_error(FileExistsError(f"invalid factorio version: '{factorio_version}'"))
        has_errors = True
    
    if has_errors:
        print("failed to run due to errors above")
        input('press [enter] to exit')
        quit(1)
    print("Ran successfuly!")
    