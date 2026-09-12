#pragma once
#include <credentialprovider.h>

class NeoFaceCredential : public ICredentialProviderCredential {
public:
    NeoFaceCredential();
    IFACEMETHODIMP QueryInterface(REFIID riid, void **ppv);
    IFACEMETHODIMP_(ULONG) AddRef();
    IFACEMETHODIMP_(ULONG) Release();
    IFACEMETHODIMP Advise(ICredentialProviderCredentialEvents *p);
    IFACEMETHODIMP UnAdvise();
    IFACEMETHODIMP SetSelected(BOOL *autoLogon);
    IFACEMETHODIMP SetDeselected();
    IFACEMETHODIMP GetFieldState(DWORD id, CREDENTIAL_PROVIDER_FIELD_STATE *s, CREDENTIAL_PROVIDER_FIELD_INTERACTIVE_STATE *i);
    IFACEMETHODIMP GetStringValue(DWORD id, LPWSTR *v);
    IFACEMETHODIMP GetBitmapValue(DWORD, HBITMAP*) { return E_NOTIMPL; }
    IFACEMETHODIMP GetCheckboxValue(DWORD, BOOL*, LPWSTR*) { return E_NOTIMPL; }
    IFACEMETHODIMP GetSubmitButtonValue(DWORD id, DWORD *adjacent);
    IFACEMETHODIMP GetComboBoxValueCount(DWORD, DWORD*, DWORD*) { return E_NOTIMPL; }
    IFACEMETHODIMP GetComboBoxValueAt(DWORD, DWORD, LPWSTR*) { return E_NOTIMPL; }
    IFACEMETHODIMP SetStringValue(DWORD, LPCWSTR) { return S_OK; }
    IFACEMETHODIMP SetCheckboxValue(DWORD, BOOL) { return S_OK; }
    IFACEMETHODIMP SetComboBoxSelectedValue(DWORD, DWORD) { return S_OK; }
    IFACEMETHODIMP CommandLinkClicked(DWORD) { return S_OK; }
    IFACEMETHODIMP GetSerialization(CREDENTIAL_PROVIDER_GET_SERIALIZATION_RESPONSE *r, CREDENTIAL_PROVIDER_CREDENTIAL_SERIALIZATION *s, LPWSTR *status, CREDENTIAL_PROVIDER_STATUS_ICON *icon);
    IFACEMETHODIMP ReportResult(NTSTATUS, NTSTATUS, LPWSTR*, CREDENTIAL_PROVIDER_STATUS_ICON*) { return S_OK; }
private:
    LONG _cRef;
    CREDENTIAL_PROVIDER_USAGE_SCENARIO _cpus;
    friend class NeoFaceProvider;
};
