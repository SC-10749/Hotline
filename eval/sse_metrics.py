"""Pure SSE parsing shared by the load scenario and its tests."""
import json


def events(lines):
    data = []
    for raw in lines:
        line = raw.decode('utf-8') if isinstance(raw, bytes) else raw
        if not line:
            if data:
                payload = '\n'.join(data)
                yield {'type': 'done'} if payload == '[DONE]' else json.loads(payload)
                data = []
        elif line.startswith('data:'):
            data.append(line[5:].lstrip())
    if data:
        raise ValueError('SSE 在完整事件结束前断开')


def percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    return round(values[min(len(values) - 1, int((len(values) - 1) * p))], 2)
