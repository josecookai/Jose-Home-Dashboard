#!/usr/bin/env python3
"""
SQLite Database Module for Jose Home Dashboard
Provides ORM-style functions for job tracking and report storage.
"""

import sqlite3
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from contextlib import contextmanager

# Register adapters for datetime handling (Python 3.12 compatibility)
def _adapt_datetime(dt):
    """Convert datetime to ISO format string for SQLite storage."""
    return dt.isoformat() if dt else None

def _convert_datetime(s):
    """Convert ISO format string back to datetime."""
    if s is None:
        return None
    try:
        return datetime.fromisoformat(s.decode() if isinstance(s, bytes) else s)
    except (ValueError, AttributeError):
        return s

sqlite3.register_adapter(datetime, _adapt_datetime)
sqlite3.register_converter("timestamp", _convert_datetime)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _expand_path(db_path: str) -> str:
    """Expand user home directory in path."""
    expanded = os.path.expanduser(db_path)
    # Also expand any environment variables
    expanded = os.path.expandvars(expanded)
    return expanded


@contextmanager
def get_connection(db_path: str):
    """Context manager for database connections."""
    expanded_path = _expand_path(db_path)
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(expanded_path), exist_ok=True)
    
    conn = None
    try:
        conn = sqlite3.connect(expanded_path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        logger.debug(f"Database connection opened: {expanded_path}")
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        raise
    finally:
        if conn:
            conn.close()
            logger.debug("Database connection closed")


def init_db(db_path: str = "~/.openclaw/workspace/dashboard.db") -> None:
    """
    Initialize the database with required tables.
    
    Tables created:
    - jobs: cron job definitions
    - job_executions: execution tracking
    - reports: generated reports
    """
    expanded_path = _expand_path(db_path)
    logger.info(f"Initializing database at: {expanded_path}")
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Create jobs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                script_path TEXT NOT NULL,
                schedule TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                priority INTEGER DEFAULT 5,
                enabled BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logger.info("Table 'jobs' created or already exists")
        
        # Create job_executions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                scheduled_at TIMESTAMP,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                status TEXT DEFAULT 'running',
                exit_code INTEGER,
                error_message TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
            )
        """)
        logger.info("Table 'job_executions' created or already exists")
        
        # Create reports table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_execution_id INTEGER NOT NULL,
                report_type TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                key_metrics_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (job_execution_id) REFERENCES job_executions(id) ON DELETE CASCADE
            )
        """)
        logger.info("Table 'reports' created or already exists")
        
        # Create indexes for better query performance
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_executions_job_id 
            ON job_executions(job_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_executions_status 
            ON job_executions(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_executions_started_at 
            ON job_executions(started_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reports_execution_id 
            ON reports(job_execution_id)
        """)
        logger.info("Database indexes created")
        
        conn.commit()
        logger.info("Database initialization complete")


def _get_or_create_job(conn: sqlite3.Connection, job_name: str) -> int:
    """Get job ID by name, creating a placeholder job if it doesn't exist."""
    cursor = conn.cursor()
    
    # Try to find existing job
    cursor.execute("SELECT id FROM jobs WHERE name = ?", (job_name,))
    row = cursor.fetchone()
    
    if row:
        return row['id']
    
    # Create a placeholder job entry
    # In production, jobs should be properly defined via migration or config
    cursor.execute("""
        INSERT INTO jobs (name, script_path, schedule, category, priority, enabled)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (job_name, f"scripts/{job_name}.py", "0 0 * * *", "general", 5, 1))
    
    job_id = cursor.lastrowid
    logger.info(f"Created placeholder job '{job_name}' with ID {job_id}")
    return job_id


def log_job_start(job_name: str, db_path: str = "~/.openclaw/workspace/dashboard.db") -> int:
    """
    Log the start of a job execution.
    
    Args:
        job_name: Name of the job
        db_path: Path to the database file
        
    Returns:
        execution_id: The ID of the newly created execution record
    """
    logger.info(f"Logging job start: {job_name}")
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Get or create job
        job_id = _get_or_create_job(conn, job_name)
        
        # Create execution record
        cursor.execute("""
            INSERT INTO job_executions (job_id, scheduled_at, started_at, status)
            VALUES (?, ?, ?, ?)
        """, (job_id, datetime.now(), datetime.now(), 'running'))
        
        execution_id = cursor.lastrowid
        conn.commit()
        
        logger.info(f"Job '{job_name}' started with execution_id: {execution_id}")
        return execution_id


def log_job_end(
    execution_id: int, 
    status: str, 
    exit_code: int, 
    error: str = None,
    db_path: str = "~/.openclaw/workspace/dashboard.db"
) -> None:
    """
    Log the completion of a job execution.
    
    Args:
        execution_id: The execution ID returned by log_job_start
        status: Final status ('success', 'failed', 'timeout', etc.)
        exit_code: Process exit code (0 for success)
        error: Error message if the job failed
        db_path: Path to the database file
    """
    logger.info(f"Logging job end: execution_id={execution_id}, status={status}, exit_code={exit_code}")
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE job_executions 
            SET completed_at = ?, status = ?, exit_code = ?, error_message = ?
            WHERE id = ?
        """, (datetime.now(), status, exit_code, error, execution_id))
        
        conn.commit()
        
        if cursor.rowcount == 0:
            logger.warning(f"No execution record found with id={execution_id}")
        else:
            logger.info(f"Job execution {execution_id} completed with status '{status}'")


def save_report(
    execution_id: int,
    report_type: str,
    title: str,
    content: str,
    metrics: Dict[str, Any],
    db_path: str = "~/.openclaw/workspace/dashboard.db"
) -> None:
    """
    Save a generated report to the database.
    
    Args:
        execution_id: The execution ID this report belongs to
        report_type: Type of report (e.g., 'bitcoin_etf', 'system_health')
        title: Report title
        content: Report content (can be markdown or plain text)
        metrics: Dictionary of key metrics to store as JSON
        db_path: Path to the database file
    """
    logger.info(f"Saving report: execution_id={execution_id}, type={report_type}, title={title}")
    
    # Serialize metrics to JSON
    metrics_json = json.dumps(metrics, default=str)
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO reports (job_execution_id, report_type, title, content, key_metrics_json)
            VALUES (?, ?, ?, ?, ?)
        """, (execution_id, report_type, title, content, metrics_json))
        
        report_id = cursor.lastrowid
        conn.commit()
        
        logger.info(f"Report saved with id={report_id}")


def get_recent_executions(days: int = 7, db_path: str = "~/.openclaw/workspace/dashboard.db") -> List[Dict]:
    """
    Get recent job executions.
    
    Args:
        days: Number of days to look back
        db_path: Path to the database file
        
    Returns:
        List of execution records as dictionaries
    """
    logger.info(f"Fetching recent executions for last {days} days")
    
    cutoff_date = datetime.now() - timedelta(days=days)
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                je.id,
                je.job_id,
                j.name as job_name,
                je.scheduled_at,
                je.started_at,
                je.completed_at,
                je.status,
                je.exit_code,
                je.error_message
            FROM job_executions je
            JOIN jobs j ON je.job_id = j.id
            WHERE je.started_at >= ?
            ORDER BY je.started_at DESC
        """, (cutoff_date,))
        
        rows = cursor.fetchall()
        executions = [dict(row) for row in rows]
        
        logger.info(f"Found {len(executions)} executions in the last {days} days")
        return executions


def get_job_success_rate(job_name: str, days: int = 30, db_path: str = "~/.openclaw/workspace/dashboard.db") -> float:
    """
    Calculate the success rate for a specific job.
    
    Args:
        job_name: Name of the job
        days: Number of days to look back
        db_path: Path to the database file
        
    Returns:
        Success rate as a float between 0.0 and 1.0
    """
    logger.info(f"Calculating success rate for job '{job_name}' over last {days} days")
    
    cutoff_date = datetime.now() - timedelta(days=days)
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN je.status = 'success' AND je.exit_code = 0 THEN 1 ELSE 0 END) as successful
            FROM job_executions je
            JOIN jobs j ON je.job_id = j.id
            WHERE j.name = ? AND je.started_at >= ?
        """, (job_name, cutoff_date))
        
        row = cursor.fetchone()
        
        if not row or row['total'] == 0:
            logger.info(f"No executions found for job '{job_name}' in the last {days} days")
            return 0.0
        
        total = row['total']
        successful = row['successful'] or 0
        rate = successful / total if total > 0 else 0.0
        
        logger.info(f"Job '{job_name}': {successful}/{total} successful ({rate:.2%})")
        return rate


# Additional utility functions for common operations

def get_job_by_name(job_name: str, db_path: str = "~/.openclaw/workspace/dashboard.db") -> Optional[Dict]:
    """Get job details by name."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs WHERE name = ?", (job_name,))
        row = cursor.fetchone()
        return dict(row) if row else None


def list_all_jobs(db_path: str = "~/.openclaw/workspace/dashboard.db") -> List[Dict]:
    """List all defined jobs."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs ORDER BY category, priority DESC, name")
        return [dict(row) for row in cursor.fetchall()]


def get_execution_reports(execution_id: int, db_path: str = "~/.openclaw/workspace/dashboard.db") -> List[Dict]:
    """Get all reports for a specific execution."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM reports 
            WHERE job_execution_id = ?
            ORDER BY created_at DESC
        """, (execution_id,))
        
        reports = []
        for row in cursor.fetchall():
            report = dict(row)
            # Deserialize metrics JSON
            if report.get('key_metrics_json'):
                report['key_metrics'] = json.loads(report['key_metrics_json'])
            reports.append(report)
        
        return reports


def delete_old_executions(days: int = 90, db_path: str = "~/.openclaw/workspace/dashboard.db") -> int:
    """
    Delete execution records older than specified days.
    Reports will be cascade deleted due to foreign key constraint.
    
    Returns:
        Number of deleted records
    """
    cutoff_date = datetime.now() - timedelta(days=days)
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM job_executions WHERE started_at < ?", (cutoff_date,))
        deleted = cursor.rowcount
        conn.commit()
        
        logger.info(f"Deleted {deleted} old execution records")
        return deleted


if __name__ == '__main__':
    # Test the module
    logger.info("Testing database module...")
    
    # Initialize database
    init_db("/tmp/test_dashboard.db")
    
    # Test logging
    exec_id = log_job_start("test_job", "/tmp/test_dashboard.db")
    
    # Test report saving
    save_report(
        exec_id,
        "test_report",
        "Test Report",
        "This is a test report content",
        {"metric1": 100, "metric2": "test"},
        "/tmp/test_dashboard.db"
    )
    
    # Test job end
    log_job_end(exec_id, "success", 0, db_path="/tmp/test_dashboard.db")
    
    # Test queries
    executions = get_recent_executions(1, "/tmp/test_dashboard.db")
    print(f"Recent executions: {executions}")
    
    success_rate = get_job_success_rate("test_job", 1, "/tmp/test_dashboard.db")
    print(f"Success rate: {success_rate}")
    
    logger.info("Database module test complete")
