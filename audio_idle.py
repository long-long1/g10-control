"""Read session metadata only. Never reads samples or changes endpoint settings."""
from audio_route import _com_thread


def inspect_idle(pair):
    import comtypes
    from pycaw.pycaw import AudioUtilities
    from pycaw.api.audiopolicy import IAudioSessionManager2, IAudioSessionControl2
    result = {'idle': False, 'endpoints': [], 'policy': 'session metadata only; no samples'}
    with _com_thread():
        enum = AudioUtilities.GetDeviceEnumerator()
        for role in ('render', 'capture'):
            row = {'role': role, 'sessions': []}
            try:
                device = enum.GetDevice(pair[role]['id'])
                manager = device.Activate(IAudioSessionManager2._iid_, comtypes.CLSCTX_ALL, None).QueryInterface(IAudioSessionManager2)
                sessions = manager.GetSessionEnumerator()
                for index in range(sessions.GetCount()):
                    session = sessions.GetSession(index).QueryInterface(IAudioSessionControl2)
                    row['sessions'].append({'pid': session.GetProcessId(), 'state': session.GetState()})
            except Exception as exc:
                row['error'] = str(exc)
            result['endpoints'].append(row)
    result['idle'] = all('error' not in row and all(item['state'] in (0, 2) for item in row['sessions'])
                         for row in result['endpoints'])
    return result
