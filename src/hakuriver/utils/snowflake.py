import snowflake


class Snowflake:
    def __init__(self, instance_id=0):
        self.gen = snowflake.SnowflakeGenerator(instance_id)

    def __call__(self):
        return next(self.gen)


# Global snowflake generator instance
_snowflake = Snowflake()


def generate_snowflake_id() -> str:
    """Generate a unique snowflake ID as a string."""
    return str(_snowflake())
