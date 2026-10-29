"""Create one stable, signed Sparkle entry; never read private signing material."""
import base64
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


def appcast(version, archive, signature):
    if not re.fullmatch(r'\d+\.\d+\.\d+', version) or len(base64.b64decode(signature, validate=True)) != 64:
        raise ValueError('Invalid version or EdDSA signature')
    ns = 'http://www.andymatuschak.org/xml-namespaces/sparkle'
    ET.register_namespace('sparkle', ns)
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    ET.SubElement(channel, 'title').text = 'Tubify'
    item = ET.SubElement(channel, 'item')
    ET.SubElement(item, 'title').text = 'Tubify ' + version
    ET.SubElement(item, '{'+ns+'}version').text = version
    ET.SubElement(item, '{'+ns+'}minimumSystemVersion').text = '12.0'
    ET.SubElement(item, 'enclosure', {
        'url': 'https://github.com/Sayarinu/YouTube-Music-App/releases/download/native-v'+version+'/'+archive.name,
        'length': str(archive.stat().st_size), 'type': 'application/octet-stream', '{'+ns+'}edSignature': signature})
    return ET.tostring(rss, encoding='utf-8', xml_declaration=True)


if __name__ == '__main__':
    Path(sys.argv[4]).write_bytes(appcast(sys.argv[1], Path(sys.argv[2]), sys.argv[3]))
