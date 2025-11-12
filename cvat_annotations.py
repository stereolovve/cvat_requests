import requests
import json
from typing import Optional, Dict, List


BASE_URL = "https:///api"
USERNAME = ""
PASSWORD = ""
TIMEOUT = 60

PROJECT_ID = None
TASK_ID = None
JOB_ID = None
ASSIGNEE = None
STATUS = None


def login():
    url = f"{BASE_URL}/auth/login"
    response = requests.post(
        url,
        json={"username": USERNAME, "password": PASSWORD},
        timeout=TIMEOUT
    )
    response.raise_for_status()
    return response.cookies


def get_jobs(cookies, project_id=None, task_id=None, job_id=None, assignee=None, status=None):
    url = f"{BASE_URL}/jobs"
    params = {}

    if project_id:
        params["project_id"] = project_id
    if task_id:
        params["task_id"] = task_id
    if job_id:
        params["id"] = job_id
    if assignee:
        params["assignee"] = assignee
    if status:
        params["status"] = status

    all_jobs = []
    page = 1

    while True:
        params["page"] = page
        response = requests.get(url, params=params, cookies=cookies, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()

        results = data.get("results", [])
        if not results:
            break

        all_jobs.extend(results)

        if not data.get("next"):
            break
        page += 1

    return all_jobs


def get_task_name(cookies, task_id):
    url = f"{BASE_URL}/tasks/{task_id}"
    try:
        response = requests.get(url, cookies=cookies, timeout=TIMEOUT)
        response.raise_for_status()
        data = response.json()
        return data.get("name", "Unknown")
    except Exception:
        return "Unknown"


def get_job_annotations(cookies, job_id):
    url = f"{BASE_URL}/jobs/{job_id}/annotations"
    response = requests.get(url, cookies=cookies, timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json()

    shapes = data.get("shapes", [])
    tracks = data.get("tracks", [])

    direct_shapes = len(shapes)

    manually_in_tracks = 0
    interpolated_in_tracks = 0

    for track in tracks:
        for shape in track.get("shapes", []):
            if shape.get("outside", False):
                continue

            if shape.get("keyframe", False):
                manually_in_tracks += 1
            else:
                interpolated_in_tracks += 1

    total_manual = direct_shapes + manually_in_tracks
    total_interpolated = interpolated_in_tracks
    total_annotations = total_manual + total_interpolated

    return {
        "direct_shapes": direct_shapes,
        "manually_in_tracks": manually_in_tracks,
        "interpolated_in_tracks": interpolated_in_tracks,
        "total_manual": total_manual,
        "total_interpolated": total_interpolated,
        "total": total_annotations
    }


def main():
    print("Login...")
    cookies = login()
    print("Login successful")

    filters_info = f"project_id={PROJECT_ID}, task_id={TASK_ID}, job_id={JOB_ID}, assignee={ASSIGNEE}, status={STATUS}"
    print(f"\nFetching jobs ({filters_info})...")
    jobs = get_jobs(cookies, project_id=PROJECT_ID, task_id=TASK_ID, job_id=JOB_ID, assignee=ASSIGNEE, status=STATUS)
    print(f"Found {len(jobs)} jobs")

    jobs_data = []
    total_manual = 0
    total_interpolated = 0

    for i, job in enumerate(jobs, 1):
        job_id = job["id"]
        task_id = job.get("task_id")
        assignee = job.get("assignee", {})
        assignee_username = assignee.get("username", "unassigned") if assignee else "unassigned"

        task_name = get_task_name(cookies, task_id) if task_id else "Unknown"

        print(f"Processing job {i}/{len(jobs)}: job_id={job_id}, task_id={task_id}, task_name='{task_name}'")

        annotations = get_job_annotations(cookies, job_id)

        total_manual += annotations["total_manual"]
        total_interpolated += annotations["total_interpolated"]

        jobs_data.append({
            "job_id": job_id,
            "task_id": task_id,
            "task_name": task_name,
            "assignee": assignee_username,
            "status": job.get("status"),
            "state": job.get("state"),
            "manual": annotations["total_manual"],
            "interpolated": annotations["total_interpolated"],
            "total": annotations["total"]
        })

    print("\n" + "="*80)
    print("STATISTICS")
    print("="*80)
    print(f"Total jobs: {len(jobs_data)}")
    print(f"Total manual annotations: {total_manual}")
    print(f"Total interpolated annotations: {total_interpolated}")
    print(f"Total annotations: {total_manual + total_interpolated}")

    print("\n" + "="*80)
    print("JOBS DETAILS")
    print("="*80)
    for job in jobs_data:
        print(f"Job {job['job_id']:<5} | Task: {job['task_name']:<30} | "
              f"{job['assignee']:<15} | State: {job['state']:<12} | "
              f"Manual: {job['manual']:>4} | Interp: {job['interpolated']:>4} | Total: {job['total']:>4}")

    results = {
        "statistics": {
            "total_jobs": len(jobs_data),
            "total_manual": total_manual,
            "total_interpolated": total_interpolated,
            "total_annotations": total_manual + total_interpolated
        },
        "jobs": jobs_data
    }

    output_file = "cvat_annotations_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {output_file}")


if __name__ == "__main__":
    main()
