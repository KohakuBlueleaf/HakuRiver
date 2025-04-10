import snowflake


class Snowflake:
    def __init__(self, instance_id=0):
        self.gen = snowflake.SnowflakeGenerator(instance_id)

    def __call__(self):
        return next(self.gen)
