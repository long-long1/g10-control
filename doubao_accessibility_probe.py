"""Read-only, status-bar-only Windows UIA inspection. Never invokes controls."""
import ctypes as c
from ctypes import wintypes as w
import json
from pathlib import Path

import comtypes
import comtypes.client
import psutil

from doubao_ui_probe import process_security
from doubao_voice import u


def inspect():
    result={'security':process_security(__import__('os').getpid()),'windows':[],
            'read_only':True,'invoked_controls':False}
    comtypes.CoInitialize()
    old_context=None
    try:
        if hasattr(u,'SetThreadDpiAwarenessContext'):
            u.SetThreadDpiAwarenessContext.argtypes=[c.c_void_p]
            u.SetThreadDpiAwarenessContext.restype=c.c_void_p
            old_context=u.SetThreadDpiAwarenessContext(c.c_void_p(-4))
        u.GetClientRect.argtypes=[w.HWND,c.POINTER(w.RECT)]
        u.GetClientRect.restype=w.BOOL
        typelib=comtypes.client.GetModule('UIAutomationCore.dll')
        automation=comtypes.client.CreateObject(typelib.CUIAutomation,interface=typelib.IUIAutomation)
        callback_type=c.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)

        @callback_type
        def visit(hwnd,_):
            name=c.create_unicode_buffer(128);u.GetClassNameW(hwnd,name,128)
            if name.value!='OimeDirectUIWindow':return True
            pid=w.DWORD();u.GetWindowThreadProcessId(hwnd,c.byref(pid))
            try:
                if '\\doubaoime\\' not in psutil.Process(pid.value).exe().casefold():return True
            except psutil.Error:return True
            rect=w.RECT();u.GetWindowRect(hwnd,c.byref(rect))
            width=rect.right-rect.left;height=rect.bottom-rect.top
            if not height or not 3.15<=width/height<=3.8 or not 140<=width<=320:return True
            client=w.RECT();u.GetClientRect(hwnd,c.byref(client))
            item={'hwnd':int(hwnd),'visible':bool(u.IsWindowVisible(hwnd)),
                  'window_size':[width,height],'client_size':[client.right,client.bottom],
                  'dpi':u.GetDpiForWindow(hwnd),'nodes':[]}
            result['windows'].append(item)
            try:
                root=automation.ElementFromHandle(hwnd)
                try:
                    legacy=root.GetCurrentPattern(10018).QueryInterface(typelib.IUIAutomationLegacyIAccessiblePattern)
                    native=legacy.GetIAccessible()
                    item['legacy']={'default_action':legacy.CurrentDefaultAction,
                                    'child_id':legacy.CurrentChildId,
                                    'native_accessible':bool(native)}
                    if native:
                        count=native.accChildCount
                        item['legacy']['child_count']=count
                        item['legacy']['children']=[]
                        for child_id in range(1,min(count,40)+1):
                            item['legacy']['children'].append({'child_id':child_id,
                                'name':native.accName[child_id],
                                'default_action':native.accDefaultAction[child_id]})
                except Exception as error:item['legacy_error']=str(error)
                walker=automation.RawViewWalker
                def walk(element,depth):
                    if depth>3 or len(item['nodes'])>=40:return
                    item['nodes'].append({'depth':depth,'name':element.CurrentName,
                                          'control_type':element.CurrentControlType,
                                          'automation_id':element.CurrentAutomationId,
                                          'invoke_available':bool(element.GetCurrentPropertyValue(30031)),
                                          'legacy_available':bool(element.GetCurrentPropertyValue(30090))})
                    child=walker.GetFirstChildElement(element)
                    while child and len(item['nodes'])<40:
                        walk(child,depth+1)
                        child=walker.GetNextSiblingElement(child)
                walk(root,0)
            except Exception as error:item['uia_error']=str(error)
            return True
        u.EnumWindows(visit,0)
    except Exception as error:result['error']=str(error)
    finally:
        if old_context:u.SetThreadDpiAwarenessContext(old_context)
        comtypes.CoUninitialize()
    output=Path(__file__).resolve().parent/'output'/'doubao-integration-analysis'
    output.mkdir(parents=True,exist_ok=True)
    tag='high' if result['security']['integrity_rid']>=0x3000 else 'medium'
    (output/f'accessibility-{tag}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'integrity':tag,'windows':len(result['windows']),
                      'node_counts':[len(x['nodes']) for x in result['windows']],
                      'error':result.get('error')}))


if __name__=='__main__':inspect()
