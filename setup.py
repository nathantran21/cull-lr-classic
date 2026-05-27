from setuptools import setup
APP = ['LR_Pick_Flagger.py']
OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'LR_Pick_Flagger.icns',
    'plist': {
        'CFBundleName': 'LR Pick Flagger',
        'CFBundleDisplayName': 'LR Pick Flagger',
        'CFBundleVersion': '1.0',
        'CFBundleIconFile': 'LR_Pick_Flagger',
    },
}
setup(app=APP, options={'py2app': OPTIONS}, setup_requires=['py2app'])
