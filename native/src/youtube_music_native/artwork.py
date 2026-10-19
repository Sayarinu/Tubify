"""Bounded disk cache for the QML engine's asynchronous artwork requests."""

from pathlib import Path

from PySide6.QtNetwork import QNetworkAccessManager, QNetworkDiskCache, QNetworkRequest
from PySide6.QtQml import QQmlNetworkAccessManagerFactory


class ArtworkNetwork(QNetworkAccessManager):
    def createRequest(self, operation, request, outgoingData=None):
        request.setAttribute(QNetworkRequest.Attribute.CacheLoadControlAttribute, QNetworkRequest.CacheLoadControl.PreferCache)
        return super().createRequest(operation, request, outgoingData)


class ArtworkCache(QQmlNetworkAccessManagerFactory):
    def __init__(self, folder):
        super().__init__()
        self.folder = str(Path(folder))

    def create(self, parent):
        manager = ArtworkNetwork(parent)
        cache = QNetworkDiskCache(manager)
        cache.setCacheDirectory(self.folder)
        cache.setMaximumCacheSize(128 * 1024 * 1024)
        manager.setCache(cache)
        return manager
