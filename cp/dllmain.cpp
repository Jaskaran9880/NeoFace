#include <windows.h>
#include <unknwn.h>
#include <new>
#include "provider.h"
#include "guid.h"

extern "C" const GUID CLSID_NeoFace =
    { 0x8f3b2c1d, 0x4e5a, 0x4b7c, { 0x9d, 0x1f, 0x2a, 0x3b, 0x4c, 0x5d, 0x6e, 0x7f } };

HINSTANCE g_hInst = NULL;
LONG g_cRef = 0;

STDAPI DllAddRef() { InterlockedIncrement(&g_cRef); return S_OK; }
STDAPI DllRelease() { InterlockedDecrement(&g_cRef); return S_OK; }

class NeoFaceFactory : public IClassFactory {
public:
    NeoFaceFactory() : _cRef(1) { DllAddRef(); }
    IFACEMETHODIMP QueryInterface(REFIID riid, void **ppv) {
        if (!ppv) return E_INVALIDARG;
        *ppv = NULL;
        if (riid == IID_IUnknown || riid == IID_IClassFactory) *ppv = (IClassFactory*)this;
        else return E_NOINTERFACE;
        AddRef();
        return S_OK;
    }
    IFACEMETHODIMP_(ULONG) AddRef() { return InterlockedIncrement(&_cRef); }
    IFACEMETHODIMP_(ULONG) Release() {
        LONG c = InterlockedDecrement(&_cRef);
        if (!c) delete this;
        return c;
    }
    IFACEMETHODIMP CreateInstance(IUnknown *outer, REFIID riid, void **ppv) {
        if (outer) return CLASS_E_NOAGGREGATION;
        NeoFaceProvider *p = new (std::nothrow) NeoFaceProvider();
        if (!p) return E_OUTOFMEMORY;
        HRESULT hr = p->QueryInterface(riid, ppv);
        p->Release();
        return hr;
    }
    IFACEMETHODIMP LockServer(BOOL lock) {
        if (lock) DllAddRef(); else DllRelease();
        return S_OK;
    }
private:
    LONG _cRef;
};

STDAPI DllGetClassObject(REFCLSID rclsid, REFIID riid, void **ppv) {
    if (rclsid != CLSID_NeoFace) return CLASS_E_CLASSNOTAVAILABLE;
    NeoFaceFactory *f = new (std::nothrow) NeoFaceFactory();
    if (!f) return E_OUTOFMEMORY;
    HRESULT hr = f->QueryInterface(riid, ppv);
    f->Release();
    return hr;
}

STDAPI DllCanUnloadNow() { return g_cRef > 0 ? S_FALSE : S_OK; }

static HRESULT RegisterServer(BOOL reg) {
    wchar_t path[MAX_PATH];
    GetModuleFileNameW(g_hInst, path, MAX_PATH);
    wchar_t clsid[64];
    StringFromGUID2(CLSID_NeoFace, clsid, 64);
    wchar_t key[128];
    wsprintfW(key, L"CLSID\\%s", clsid);
    if (reg) {
        HKEY h;
        RegCreateKeyExW(HKEY_CLASSES_ROOT, key, 0, NULL, 0, KEY_WRITE, NULL, &h, NULL);
        RegSetValueExW(h, NULL, 0, REG_SZ, (BYTE*)L"NeoFace Unlock", 30);
        RegCloseKey(h);
        wsprintfW(key, L"CLSID\\%s\\InprocServer32", clsid);
        RegCreateKeyExW(HKEY_CLASSES_ROOT, key, 0, NULL, 0, KEY_WRITE, NULL, &h, NULL);
        RegSetValueExW(h, NULL, 0, REG_SZ, (BYTE*)path, (wcslen(path)+1)*2);
        RegSetValueExW(h, L"ThreadingModel", 0, REG_SZ, (BYTE*)L"Apartment", 18);
        RegCloseKey(h);
    } else {
        wsprintfW(key, L"CLSID\\%s\\InprocServer32", clsid);
        RegDeleteKeyW(HKEY_CLASSES_ROOT, key);
        wsprintfW(key, L"CLSID\\%s", clsid);
        RegDeleteKeyW(HKEY_CLASSES_ROOT, key);
    }
    return S_OK;
}

STDAPI DllRegisterServer() { return RegisterServer(TRUE); }
STDAPI DllUnregisterServer() { return RegisterServer(FALSE); }

BOOL APIENTRY DllMain(HINSTANCE h, DWORD r, LPVOID) {
    if (r == DLL_PROCESS_ATTACH) { g_hInst = h; DisableThreadLibraryCalls(h); }
    return TRUE;
}
