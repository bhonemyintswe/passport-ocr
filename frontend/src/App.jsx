import { useState, useEffect } from 'react';
import LoginPage from './components/LoginPage';
import UploadPage from './components/UploadPage';
import DataTable from './components/DataTable';
import { isAuthenticated, logout } from './api';

function App() {
  const [authenticated, setAuthenticated] = useState(false);
  const [passports, setPassports] = useState([]);
  const [step, setStep] = useState('upload'); // 'upload' | 'review'

  useEffect(() => {
    setAuthenticated(isAuthenticated());
  }, []);

  const handleLoginSuccess = () => {
    setAuthenticated(true);
  };

  const handleLogout = () => {
    logout();
    setAuthenticated(false);
    setPassports([]);
    setStep('upload');
  };

  const handleOCRComplete = (extractedPassports) => {
    setPassports(extractedPassports);
    setStep('review');
  };

  const handleBackToUpload = () => {
    setPassports([]);
    setStep('upload');
  };

  if (!authenticated) {
    return <LoginPage onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-3">
              <svg className="w-8 h-8 text-blue-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="4" width="18" height="16" rx="2" ry="2"/>
                <circle cx="12" cy="10" r="3"/>
                <path d="M7 16h10"/>
              </svg>
              <h1 className="text-xl font-semibold text-gray-900">Passport OCR</h1>
            </div>

            {/* Step Indicator */}
            <div className="hidden sm:flex items-center gap-2">
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${step === 'upload' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-500'}`}>
                1. Upload
              </span>
              <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
              <span className={`px-3 py-1 rounded-full text-sm font-medium ${step === 'review' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-500'}`}>
                2. Review & Export
              </span>
            </div>

            <button
              onClick={handleLogout}
              className="text-sm text-gray-600 hover:text-gray-900 font-medium"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {step === 'upload' ? (
          <UploadPage onOCRComplete={handleOCRComplete} />
        ) : (
          <DataTable
            passports={passports}
            setPassports={setPassports}
            onBack={handleBackToUpload}
          />
        )}
      </main>
    </div>
  );
}

export default App;
