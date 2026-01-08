import datetime
import json
import platform

from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from pprint import pprint

import docker
from swebench.harness.constants import KEY_INSTANCE_ID, KEY_PREDICTION, KEY_MODEL, SWEbenchInstance
from swebench.harness.docker_utils import clean_images, list_images
from swebench.harness.reporting import make_run_report
from swebench.harness.run_evaluation import run_instances

if platform.system() == "Windows":
    from pathlib import Path

    _real_write_text = Path.write_text


    def write_text_lf(self, data, encoding=None, errors=None, newline=None):
        # Force LF when caller didn't explicitly request something else
        if newline is None:
            newline = "\n"
        return _real_write_text(self, data, encoding=encoding, errors=errors, newline=newline)


    Path.write_text = write_text_lf


def load_datapoint(datapoint_path: str):
    with open(datapoint_path, "r") as f:
        return json.load(f)


def run_validation(
        dataset: [SWEbenchInstance],
        predictions: dict,
        max_workers: int,
        cache_level: str,
        clean: bool,
        open_file_limit: int,
        timeout: int,
        instance_image_tag: str = "latest",
        env_image_tag: str = "latest",
        report_dir: str = ".",
):
    force_rebuild, rewrite_reports, modal, namespace = False, False, False, None
    ts = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H-%M-%S.%fZ")
    run_id = f"run_{ts}"

    # set open file limit
    assert len(run_id) > 0, "Run ID must be provided"
    if report_dir is not None:
        report_dir = Path(report_dir)
        if not report_dir.exists():
            report_dir.mkdir(parents=True)

    # run instances locally
    if platform.system() == "Linux":
        import resource
        resource.setrlimit(resource.RLIMIT_NOFILE, (open_file_limit, open_file_limit))
    client = docker.from_env()

    existing_images = list_images(client)
    if not dataset:
        print("No instances to run.")
    else:
        run_instances(
            predictions,
            dataset,
            cache_level,
            clean,
            force_rebuild,
            max_workers,
            run_id,
            timeout,
            namespace=namespace,
            instance_image_tag=instance_image_tag,
            env_image_tag=env_image_tag,
            rewrite_reports=rewrite_reports,
        )

    # clean images + make final report
    clean_images(client, existing_images, cache_level, clean)
    return make_run_report(
        predictions,
        dataset,
        run_id,
        client,
        namespace,
        instance_image_tag,
        env_image_tag,
    )


def main(datapoint_path: str):
    datapoint = load_datapoint(datapoint_path)
    prediction = {
        KEY_INSTANCE_ID: datapoint["instance_id"],
        KEY_PREDICTION: datapoint["patch"],
        KEY_MODEL: "shmold",  # TODO: decent model name
    }
    dataset = [datapoint]

    run_report = run_validation(
        dataset=dataset,
        max_workers=8,
        cache_level="",
        clean=False,
        open_file_limit=1700,
        timeout=1770,
        predictions={prediction[KEY_INSTANCE_ID]: prediction, }
    )
    pprint(run_report)
    return


pass

if __name__ == "__main__":
    parser = ArgumentParser(
        description="Run SWE-bench data point validation for the given data points.",
        formatter_class=ArgumentDefaultsHelpFormatter,
    )
    args = parser.parse_args()
    main(**vars(args), datapoint_path='./data_points/astropy__astropy-11693.json')
