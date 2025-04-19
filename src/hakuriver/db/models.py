import datetime
import json
import peewee

db = peewee.SqliteDatabase(None)  # Initialize with None


class BaseModel(peewee.Model):
    class Meta:
        database = db


class Node(BaseModel):
    hostname = peewee.CharField(unique=True, primary_key=True)
    url = peewee.CharField()  # Runner URL, e.g., http://192.168.1.101:8001
    total_cores = peewee.IntegerField()
    last_heartbeat = peewee.DateTimeField(default=datetime.datetime.now)
    status = peewee.CharField(default="online")  # 'online', 'offline'
    cpu_percent = peewee.FloatField(null=True)
    memory_percent = peewee.FloatField(null=True)
    memory_used_bytes = peewee.BigIntegerField(
        null=True
    )  # Use BigIntegerField for bytes
    memory_total_bytes = peewee.BigIntegerField(
        null=True
    )  # Use BigIntegerField for bytes
    numa_topology = peewee.TextField(null=True)  # Store NUMA info as JSON string

    def get_numa_topology(self) -> dict | None:
        """Parses the stored JSON string into a dictionary."""
        if not self.numa_topology:
            return None
        try:
            return {
                int(key): value for key, value in json.loads(self.numa_topology).items()
            }
        except json.JSONDecodeError:
            # Log this error? Maybe in the calling function.
            return None  # Return None if parsing fails

    def set_numa_topology(self, topology: dict | None):
        """Stores the topology dictionary as a JSON string."""
        if topology is None:
            self.numa_topology = None
        else:
            self.numa_topology = json.dumps(topology)


class Task(BaseModel):
    task_id = peewee.IntegerField(primary_key=True)
    command = peewee.TextField()
    arguments = peewee.TextField()  # Store as JSON string
    env_vars = peewee.TextField()  # Store as JSON string
    required_cores = peewee.IntegerField()
    status = peewee.CharField(
        default="pending"
    )  # pending, assigning, running, completed, failed, killed, lost
    assigned_node = peewee.ForeignKeyField(Node, backref="tasks", null=True)
    stdout_path = peewee.TextField()
    stderr_path = peewee.TextField()
    exit_code = peewee.IntegerField(null=True)
    error_message = peewee.TextField(null=True)
    submitted_at = peewee.DateTimeField(default=datetime.datetime.now)
    started_at = peewee.DateTimeField(null=True)
    completed_at = peewee.DateTimeField(null=True)
    assignment_suspicion_count = peewee.IntegerField(default=0)
    required_memory_bytes = peewee.BigIntegerField(null=True)
    systemd_unit_name = peewee.CharField(null=True)  # Store the transient unit name
    target_numa_node_id = peewee.IntegerField(
        null=True
    )  # Target NUMA node on the assigned_node
    batch_id = peewee.BigIntegerField(
        null=True, index=True
    )  # ID linking tasks submitted together

    def get_arguments(self):
        try:
            return json.loads(self.arguments) if self.arguments else []
        except json.JSONDecodeError:
            return []  # Or handle error appropriately

    def set_arguments(self, args_list):
        self.arguments = json.dumps(args_list or [])

    def get_env_vars(self):
        try:
            return json.loads(self.env_vars) if self.env_vars else {}
        except json.JSONDecodeError:
            return {}

    def set_env_vars(self, env_dict):
        self.env_vars = json.dumps(env_dict or [])


def initialize_database(db_file_path: str):
    """Connects to the database and creates tables if they don't exist."""
    try:
        # Explicitly set the database path for the global 'db' object
        db.init(db_file_path)
        db.connect()
        db.create_tables([Node, Task], safe=True)
        print(f"Database initialized at: {db_file_path}")
    except peewee.OperationalError as e:
        print(f"Error initializing database '{db_file_path}': {e}")
        raise
