from django.core import checks


@checks.register()
def test_redis(app_configs, **kwargs):
    from django_rq.queues import get_queue
    from django_rq.workers import Worker

    errors = []

    try:
        queue = get_queue()
        workers = Worker.all(queue.connection)
    except Exception as e:
        conn_settings = queue.connection.connection_pool.connection_kwargs
        errors.append(checks.Critical("Could not connect to Redis (%s)" % (e),
            hint="Make sure Redis is running on %(host)s:%(port)s" % (conn_settings),
            id="pootle.E001",
        ))
    else:
        if not workers or workers[0].stopped:
            errors.append(checks.Warning("No RQ Worker running.",
                hint="Run new workers with manage.py rqworker",
                id="pootle.E002",
            ))

    return errors
