from cirrus.core.utils import misc


def test_get_cirrus_geo_requirements():
    assert misc.get_cirrus_geo_requirements() == [
        "pyyaml~=6.0",
        "click~=8.0",
        "click-plugins~=1.1",
        "rich~=10.6",
        "cfn-flip~=1.2",
        "boto3-utils~=0.4.1",
        "boto3>=1.26.0",
        "python-json-logger~=2.0",
        "jsonpath-ng>=1.5.3",
        "python-dateutil~=2.8.2",
    ]
