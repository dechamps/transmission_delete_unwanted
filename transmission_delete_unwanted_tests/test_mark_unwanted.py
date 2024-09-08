import pytest
import transmission_delete_unwanted.mark_unwanted


@pytest.fixture(name="run")
def _fixture_run(transmission_url):
    return lambda *kargs, **kwargs: transmission_delete_unwanted.mark_unwanted.run(
        ["--transmission-url", transmission_url] + list(kargs), **kwargs
    )


def test_noop(run):
    run()
