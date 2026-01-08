import datetime
import json
import platform
import docker

from argparse import ArgumentParser, ArgumentDefaultsHelpFormatter
from pathlib import Path

from swebench.harness.constants import KEY_INSTANCE_ID, KEY_PREDICTION, KEY_MODEL, RUN_EVALUATION_LOG_DIR, LOG_REPORT, \
    SWEbenchInstance
from swebench.harness.docker_utils import clean_images, list_images
from swebench.harness.reporting import make_run_report
from swebench.harness.run_evaluation import run_instances, build_env_images


TIMEOUT = 3_600  # 1 hr should be enough to build images & run tests
MAX_WORKERS = 1
CLEAN = False
CACHE_LEVEL = "env"
OPEN_FILE_LIMIT = 4096
MODEL_NAME = "shmold"
REQUIRED_SWEBENCH_DATAPOINT_FIELDS: set[str] = {
    "instance_id",
    "repo",
    "base_commit",
    "problem_statement",
    "patch",
    "test_patch",
    "environment_setup_commit",
    "FAIL_TO_PASS",
    "PASS_TO_PASS",
}

if platform.system() == "Windows":  # A monkey-patch to make it work under Windows
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
        run_id: str,
        cache_level: str,
        clean: bool,
        open_file_limit: int,
        timeout: int,
        instance_image_tag: str = "latest",
        env_image_tag: str = "latest",
        report_dir: str = ".",
):
    force_rebuild, rewrite_reports, modal, namespace = False, False, False, None

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
        dataset,
        run_id,
        client,
        namespace,
        instance_image_tag,
        env_image_tag,
    )


def main(datapoint_path: str):
    datapoint = load_datapoint(datapoint_path)
    if REQUIRED_SWEBENCH_DATAPOINT_FIELDS - datapoint.keys():
        print(f"Datapoint fields are missing: {REQUIRED_SWEBENCH_DATAPOINT_FIELDS - datapoint.keys()}")
        return -1
    prediction = {
        KEY_INSTANCE_ID: datapoint["instance_id"],
        KEY_PREDICTION: datapoint["patch"],
        KEY_MODEL: MODEL_NAME,
    }
    dataset = [SWEbenchInstance(**datapoint)]
    ts = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H-%M-%S.%fZ")
    run_id = f"run_{ts}"

    run_report_path = run_validation(
        dataset=dataset,
        max_workers=MAX_WORKERS,
        run_id=run_id,
        cache_level=CACHE_LEVEL,
        clean=CLEAN,
        open_file_limit=OPEN_FILE_LIMIT,
        timeout=TIMEOUT,
        predictions={prediction[KEY_INSTANCE_ID]: prediction, },
    )
    with open(run_report_path, "r") as f:
        run_report = json.load(f)
        # Resolved means f2p & p&p are both 100% success, see swebench.harness.gradin.get_resolution_status
        num_passed = run_report["resolved_instances"]
        if num_passed == 0:
            print(
                f"Not all tests in FAIL_TO_PASS and PASS_TO_PASS passed, "
                f"see {RUN_EVALUATION_LOG_DIR / run_id / MODEL_NAME / prediction[KEY_INSTANCE_ID] / LOG_REPORT}"
            )
            return -1
    return 0


pass

if __name__ == "__main__":
    parser = ArgumentParser(
        description="Run SWE-bench data point validation for the given data points.",
        formatter_class=ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-p",
        "--datapoint_path",
        type=str,
        help="Datapoint path",
        required=True,
    )
    args = parser.parse_args()
    exit(main(**vars(args)))
