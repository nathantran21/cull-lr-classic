from setuptools import setup

APP = ['LR_Pick_Flagger_webview.py']
OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'LR_Pick_Flagger.icns',
    'packages': ['webview', 'bottle'],
    'excludes': ['tkinter'],
    'plist': {
        'CFBundleName': 'LR Pick Flagger',
        'CFBundleDisplayName': 'LR Pick Flagger',
        'CFBundleVersion': '2.0',
        'CFBundleShortVersionString': '2.0',
        'CFBundleIdentifier': 'com.nathantran.lr-pick-flagger',
        'CFBundleIconFile': 'LR_Pick_Flagger',
        'NSHighResolutionCapable': True,
        'NSHumanReadableDescription': 'Flag Pixieset favorites as picks in Lightroom Classic',
        'CFBundleDocumentTypes': [],
    },
    'resources': ['LR Pick Flagger (standalone).html'],
}
setup(
    app=APP,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
