"""Sparkle owns macOS verification, installation, authorization and relaunch UI."""
from pathlib import Path
import sys


class MacUpdater:
    def __init__(self, prepare_restart):
        import objc
        from Foundation import NSObject
        framework = Path(sys.executable).resolve().parents[1] / 'Frameworks' / 'Sparkle.framework'
        namespace = {}
        objc.loadBundle('Sparkle', namespace, bundle_path=str(framework))

        class Delegate(NSObject):
            def feedURLStringForUpdater_(self, updater):
                return self.feed

            def updaterWillRelaunchApplication_(self, updater):
                prepare_restart()

        self.delegate = Delegate.alloc().init()
        self.controller = objc.lookUpClass('SPUStandardUpdaterController').alloc().initWithStartingUpdater_updaterDelegate_userDriverDelegate_(False, self.delegate, None)

    def install(self, tag):
        self.delegate.feed = 'https://github.com/Sayarinu/YouTube-Music-App/releases/download/' + tag + '/appcast.xml'
        self.controller.startUpdater()
        self.controller.checkForUpdates_(None)
