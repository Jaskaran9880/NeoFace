#include "provider.h"
#include "credential.h"
#include "guid.h"
#include <new>
#include <shlwapi.h>

NeoFaceProvider::NeoFaceProvider() : _cRef(1), _cred(NULL), _cpus(CPUS_LOGON) {
    DllAddRef();
}

NeoFaceProvider::~NeoFaceProvider() {
    if (_cred) _cred->Release();
    DllRelease();
}

HRESULT NeoFaceProvider::QueryInterface(REFIID riid, void **ppv) {
    if (!ppv) return E_INVALIDARG;
    *ppv = NULL;
    if (riid == IID_IUnknown || riid == IID_ICredentialProvider) *ppv = (ICredentialProvider*)this;
    else return E_NOINTERFACE;
    AddRef();
    return S_OK;
}

ULONG NeoFaceProvider::AddRef() { return InterlockedIncrement(&_cRef); }
ULONG NeoFaceProvider::Release() {
    LONG c = InterlockedDecrement(&_cRef);
    if (!c) delete this;
    return c;
}

HRESULT NeoFaceProvider::SetUsageScenario(CREDENTIAL_PROVIDER_USAGE_SCENARIO cpus, DWORD flags) {
    _cpus = cpus;
    if (_cpus != CPUS_LOGON && _cpus != CPUS_UNLOCK_WORKSTATION) return E_NOTIMPL;
    return S_OK;
}

HRESULT NeoFaceProvider::SetSerialization(const CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION*) { return S_OK; }
HRESULT NeoFaceProvider::Advise(ICredentialProviderEvents*, UINT_PTR) { return S_OK; }
HRESULT NeoFaceProvider::UnAdvise() { return S_OK; }
HRESULT NeoFaceProvider::GetFieldDescriptorCount(DWORD *n) { *n = 2; return S_OK; }
HRESULT NeoFaceProvider::GetFieldDescriptorAt(DWORD i, CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR **p) {
    if (i > 1) return E_INVALIDARG;
    CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR *d = (CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR*)CoTaskMemAlloc(sizeof(CREDENTIAL_PROVIDER_FIELD_DESCRIPTOR));
    if (!d) return E_OUTOFMEMORY;
    d->dwFieldID = i;
    d->pszLabel = NULL;
    d->guidFieldType = GUID_NULL;
    if (i == 0) {
        d->cpft = CPFT_LARGE_TEXT;
    } else {
        d->cpft = CPFT_SUBMIT_BUTTON;
        SHStrDupW(L"Unlock with face", &d->pszLabel);
    }
    *p = d;
    return S_OK;
}

HRESULT NeoFaceProvider::GetCredentialCount(DWORD *n, DWORD *d, BOOL *a) {
    *n = 1; *d = (DWORD)-1; *a = FALSE;
    return S_OK;
}

HRESULT NeoFaceProvider::GetCredentialAt(DWORD i, ICredentialProviderCredential **c) {
    if (i != 0) return E_INVALIDARG;
    if (!_cred) _cred = new (std::nothrow) NeoFaceCredential();
    if (!_cred) return E_OUTOFMEMORY;
    _cred->_cpus = _cpus;
    return _cred->QueryInterface(IID_ICredentialProviderCredential, (void**)c);
}
