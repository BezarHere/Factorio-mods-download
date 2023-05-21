import glassy.utils as gutils
import manger
# import gui
import storge

# IN_GUI = False

url_samples = r"""
https://mods.manger.com/mod/industrial-warptorio2
https://mods.manger.com/mod/Explosive_biters
"""

def center(t: str, to: int, b: str = ' '):
    to = (to - len(t)) // 2
    for i in range(to):
        t = b + t + b
    return t

def in_gui_process():
    ...
    # gui.start()

def in_consol_process():
    while True:
        promt = input('MOD URL:')
        args = gutils.breakup_args(promt)
        url = args[-1].strip()
        args = gutils.args_to_dict(args[:-1])
        manger.announce(args, level=8)
        manger.download_and_process_mod(url, args=args)

def main():
    title = f'[ [ {storge.title} {storge.version} ] ]\n{storge.input_hint}\n*-* {storge.author} *-*'
    manger.announce_title(
        gutils.join((center(i, 100) for i in title.splitlines()),'\n')
    )
    manger.load_data()
    manger.check_for_errors()
    manger.update_cache()
    manger.save_cache_to_json()
    in_consol_process()
    # if IN_GUI:
    #     in_gui_process()
    # else:
    #     in_consol_process()

if __name__ == '__main__':
    main()
