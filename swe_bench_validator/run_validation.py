import json
import platform
import time

from swebench.harness.constants import SWEbenchInstance

if platform.system() == "Linux":
    import resource

from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from pathlib import Path
from pprint import pprint

import docker
from swebench import KEY_INSTANCE_ID, run_evaluation, list_images, build_env_images, KEY_PREDICTION, KEY_MODEL
from swebench.harness.docker_utils import clean_images
from swebench.harness.modal_eval import validate_modal_credentials, run_instances_modal
from swebench.harness.reporting import make_run_report
from swebench.harness.run_evaluation import get_dataset_from_preds, run_instances
from swebench.harness.utils import load_swebench_dataset


# import from swebench.harness import run_evaluation


def load_datapoint(datapoint_path: str):
    with open(datapoint_path, "r") as f:
        return json.load(f)


def run_validation(
        full_dataset: [SWEbenchInstance],
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
    run_id = f"run_{str(time.time())}"
    # run_id = f"run_{str(datetime.now().isoformat())}"

    # set open file limit
    assert len(run_id) > 0, "Run ID must be provided"
    if report_dir is not None:
        report_dir = Path(report_dir)
        if not report_dir.exists():
            report_dir.mkdir(parents=True)

    dataset = full_dataset

    # run instances locally
    if platform.system() == "Linux":
        resource.setrlimit(resource.RLIMIT_NOFILE, (open_file_limit, open_file_limit))
    client = docker.from_env()

    existing_images = list_images(client)
    if not dataset:
        print("No instances to run.")
    else:
        # build environment images + run instances
        if namespace is None and not rewrite_reports:
            build_env_images(
                client,
                dataset,
                force_rebuild,
                max_workers,
                namespace,
                instance_image_tag,
                env_image_tag,
            )
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
        full_dataset,
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
        KEY_MODEL: "gold",  # TODO: decent model name
    }
    dataset = [datapoint]

    run_report = run_validation(
        full_dataset=dataset,
        max_workers=8,
        cache_level="",
        clean=False,
        open_file_limit=1700,
        timeout=1770,
        predictions={prediction[KEY_INSTANCE_ID]: prediction, }
    )
    pprint(run_report)
    return

    # run_report = run_evaluation(
    #     dataset_name=datapoint['_download_metadata']['dataset_name'],
    #     split=datapoint['_download_metadata']['split'],
    #     instance_ids=[datapoint['instance_id']],
    #     predictions_path='gold',
    #     max_workers=8,
    #     force_rebuild=False,
    #     cache_level="",
    #     clean=False,
    #     open_file_limit=1700,
    #     run_id="111",
    #     timeout=1770,
    #     namespace=None,
    #     rewrite_reports=False,
    #     modal=False
    # )
    # pprint(run_report)


pass

if __name__ == "__main__":
    parser = ArgumentParser(
        description="Run SWE-bench data point validation for the given data points.",
        formatter_class=ArgumentDefaultsHelpFormatter,
    )
    args = parser.parse_args()
    main(**vars(args), datapoint_path='./data_points/astropy__astropy-11693.json')
