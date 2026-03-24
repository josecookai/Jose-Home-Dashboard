"""
Utils package for Jose Home Dashboard.
"""

from .database import (
    init_db,
    log_job_start,
    log_job_end,
    save_report,
    get_recent_executions,
    get_job_success_rate,
    get_job_by_name,
    list_all_jobs,
    get_execution_reports,
    delete_old_executions,
)

__all__ = [
    'init_db',
    'log_job_start',
    'log_job_end',
    'save_report',
    'get_recent_executions',
    'get_job_success_rate',
    'get_job_by_name',
    'list_all_jobs',
    'get_execution_reports',
    'delete_old_executions',
]
