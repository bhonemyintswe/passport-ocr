import { useState, useEffect, useRef, useCallback } from 'react';
import { exportToExcel } from '../api';

function DataTable({ passports, setPassports, onBack }) {
  const [exporting, setExporting] = useState(false);
  const [editingCell, setEditingCell] = useState(null);
  const [selectedIndex, setSelectedIndex] = useState(0);

  // Resizable panel state
  const [leftPanelWidth, setLeftPanelWidth] = useState(60);
  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef(null);

  // Image zoom state
  const [zoom, setZoom] = useState(100);
  const [isPanning, setIsPanning] = useState(false);
  const [panPosition, setPanPosition] = useState({ x: 0, y: 0 });
  const [panStart, setPanStart] = useState({ x: 0, y: 0 });

  // Image rotation state
  const [imageRotation, setImageRotation] = useState(0);

  useEffect(() => {
    if (passports.length > 0 && selectedIndex >= passports.length) {
      setSelectedIndex(0);
    }
  }, [passports, selectedIndex]);

  // Reset zoom and rotation when selecting different passport
  useEffect(() => {
    setZoom(100);
    setPanPosition({ x: 0, y: 0 });
    setImageRotation(0);
  }, [selectedIndex]);

  // Handle panel resize
  const handleMouseDown = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleMouseMove = useCallback((e) => {
    if (!isDragging || !containerRef.current) return;
    const containerRect = containerRef.current.getBoundingClientRect();
    const newWidth = ((e.clientX - containerRect.left) / containerRect.width) * 100;
    setLeftPanelWidth(Math.min(80, Math.max(30, newWidth)));
  }, [isDragging]);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
  }, []);

  useEffect(() => {
    if (isDragging) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = 'col-resize';
      document.body.style.userSelect = 'none';
    } else {
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
  }, [isDragging, handleMouseMove, handleMouseUp]);

  // Zoom handlers
  const handleZoomIn = () => setZoom(z => Math.min(300, z + 25));
  const handleZoomOut = () => setZoom(z => Math.max(25, z - 25));
  const handleZoomReset = () => {
    setZoom(100);
    setPanPosition({ x: 0, y: 0 });
  };

  const handleWheel = (e) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -10 : 10;
    setZoom(z => Math.min(300, Math.max(25, z + delta)));
  };

  // Pan handlers
  const handlePanStart = (e) => {
    if (zoom > 100) {
      setIsPanning(true);
      setPanStart({ x: e.clientX - panPosition.x, y: e.clientY - panPosition.y });
    }
  };

  const handlePanMove = (e) => {
    if (isPanning && zoom > 100) {
      setPanPosition({
        x: e.clientX - panStart.x,
        y: e.clientY - panStart.y
      });
    }
  };

  const handlePanEnd = () => {
    setIsPanning(false);
  };

  // Rotation handlers
  const handleRotateLeft = () => setImageRotation(r => r - 90);
  const handleRotateRight = () => setImageRotation(r => r + 90);
  const handleRotateReset = () => setImageRotation(0);

  // Name fields that should be uppercase
  const nameFields = ['first_name', 'middle_name', 'last_name'];

  const columns = [
    { key: 'first_name', label: 'First Name', width: 'w-24' },
    { key: 'middle_name', label: 'Middle', width: 'w-20' },
    { key: 'last_name', label: 'Last Name', width: 'w-24' },
    { key: 'gender', label: 'Sex', width: 'w-12' },
    { key: 'date_of_birth', label: 'DOB', width: 'w-24' },
    { key: 'nationality', label: 'Nat.', width: 'w-14' },
    { key: 'passport_number', label: 'Passport No.', width: 'w-28' },
  ];

  const handleCellChange = (index, field, value) => {
    const updated = [...passports];
    const finalValue = nameFields.includes(field) ? value.toUpperCase() : value;
    // Remove from low_confidence_fields when edited
    const lowConfidence = (updated[index].low_confidence_fields || []).filter(f => f !== field);
    updated[index] = { ...updated[index], [field]: finalValue, low_confidence_fields: lowConfidence };
    setPassports(updated);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' || e.key === 'Tab') {
      setEditingCell(null);
    }
    if (e.key === 'Escape') {
      setEditingCell(null);
    }
  };

  const addRow = () => {
    const newPassport = {
      first_name: '',
      middle_name: '',
      last_name: '',
      gender: '',
      date_of_birth: '',
      nationality: '',
      passport_number: '',
      thumbnail: '',
      full_image: '',
      confidence: 0,
      low_confidence_fields: [],
    };
    setPassports([...passports, newPassport]);
    setSelectedIndex(passports.length);
  };

  const deleteRow = (index) => {
    const newPassports = passports.filter((_, i) => i !== index);
    setPassports(newPassports);
    if (selectedIndex >= newPassports.length) {
      setSelectedIndex(Math.max(0, newPassports.length - 1));
    }
  };

  const clearAll = () => {
    if (window.confirm('Are you sure you want to clear all data?')) {
      setPassports([]);
      setSelectedIndex(0);
    }
  };

  const handleExport = async () => {
    if (passports.length === 0) {
      alert('No data to export.');
      return;
    }

    const uppercasePassports = passports.map(p => ({
      ...p,
      first_name: (p.first_name || '').toUpperCase(),
      middle_name: (p.middle_name || '').toUpperCase(),
      last_name: (p.last_name || '').toUpperCase(),
    }));

    setExporting(true);
    try {
      await exportToExcel(uppercasePassports);
    } catch (err) {
      alert('Failed to export data. Please try again.');
    } finally {
      setExporting(false);
    }
  };

  const handleRowClick = (index) => {
    setSelectedIndex(index);
  };

  const isEmpty = (value) => !value || value.trim() === '';

  const isLowConfidence = (passport, field) => {
    return passport.low_confidence_fields && passport.low_confidence_fields.includes(field);
  };

  const getCellStyle = (passport, field) => {
    if (isLowConfidence(passport, field)) {
      return 'bg-amber-100 border-l-2 border-l-amber-500'; // Yellow for low confidence
    }
    if (isEmpty(passport[field]) && field !== 'middle_name') {
      return 'bg-red-50'; // Red for empty required
    }
    return '';
  };

  const selectedPassport = passports[selectedIndex] || null;

  // Count low confidence fields
  const lowConfidenceCount = passports.reduce((acc, p) =>
    acc + (p.low_confidence_fields?.length || 0), 0
  );

  return (
    <div>
      {/* Header Actions */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">Review Extracted Data</h2>
          <p className="text-gray-600 mt-1">
            {passports.length} passport(s) found.
            {lowConfidenceCount > 0 && (
              <span className="text-amber-600 ml-2">
                {lowConfidenceCount} field(s) need review
              </span>
            )}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={onBack}
            className="px-4 py-2 text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            Back
          </button>
          <button
            onClick={addRow}
            className="px-4 py-2 text-blue-700 bg-blue-50 border border-blue-200 rounded-lg hover:bg-blue-100 transition flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Add Row
          </button>
          <button
            onClick={clearAll}
            className="px-4 py-2 text-red-700 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100 transition flex items-center gap-2"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
            Clear All
          </button>
          <button
            onClick={handleExport}
            disabled={exporting || passports.length === 0}
            className="px-6 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition flex items-center gap-2"
          >
            {exporting ? (
              <>
                <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                Exporting...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                Export to Excel
              </>
            )}
          </button>
        </div>
      </div>

      {passports.length === 0 ? (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-12 text-center">
          <svg className="w-16 h-16 text-gray-300 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          <p className="text-gray-500">No data to display. Go back to upload passport images.</p>
        </div>
      ) : (
        <div ref={containerRef} className="flex flex-col lg:flex-row relative">
          {/* Left: Data Table */}
          <div style={{ width: `${leftPanelWidth}%` }} className="hidden lg:block">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden mr-2">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      <th className="px-2 py-2 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider w-14">
                        #
                      </th>
                      {columns.map((col) => (
                        <th
                          key={col.key}
                          className={`px-2 py-2 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider ${col.width}`}
                        >
                          {col.label}
                        </th>
                      ))}
                      <th className="px-2 py-2 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider w-12">
                        Del
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {passports.map((passport, index) => (
                      <tr
                        key={index}
                        onClick={() => handleRowClick(index)}
                        className={`cursor-pointer transition-colors ${
                          selectedIndex === index
                            ? 'bg-blue-50 border-l-4 border-l-blue-500'
                            : 'hover:bg-gray-50'
                        }`}
                      >
                        <td className="px-2 py-1">
                          <div className="flex items-center gap-1">
                            <span className="text-gray-500 text-xs">{index + 1}</span>
                            {passport.thumbnail && (
                              <img
                                src={`data:image/jpeg;base64,${passport.thumbnail}`}
                                alt=""
                                className="w-8 h-8 object-cover rounded border border-gray-200"
                              />
                            )}
                            {passport.confidence > 0 && passport.confidence < 0.7 && (
                              <span className="text-amber-500" title="Low confidence">
                                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                                  <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
                                </svg>
                              </span>
                            )}
                          </div>
                        </td>

                        {columns.map((col) => (
                          <td
                            key={col.key}
                            className={`px-2 py-1 ${col.width} ${getCellStyle(passport, col.key)}`}
                            onClick={(e) => e.stopPropagation()}
                          >
                            {editingCell === `${index}-${col.key}` ? (
                              <input
                                type="text"
                                value={passport[col.key] || ''}
                                onChange={(e) => handleCellChange(index, col.key, e.target.value)}
                                onBlur={() => setEditingCell(null)}
                                onKeyDown={handleKeyDown}
                                className={`w-full px-1 py-0.5 border border-blue-400 rounded text-sm focus:outline-none focus:ring-1 focus:ring-blue-200 ${
                                  nameFields.includes(col.key) ? 'uppercase' : ''
                                }`}
                                autoFocus
                                onClick={(e) => e.stopPropagation()}
                              />
                            ) : (
                              <div
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setEditingCell(`${index}-${col.key}`);
                                  setSelectedIndex(index);
                                }}
                                className={`editable-cell px-1 py-0.5 rounded min-h-[24px] text-sm truncate ${
                                  isEmpty(passport[col.key])
                                    ? 'text-gray-400 italic text-xs'
                                    : 'text-gray-900'
                                } ${nameFields.includes(col.key) ? 'uppercase' : ''}`}
                                title={`${passport[col.key] || 'Click to edit'}${isLowConfidence(passport, col.key) ? ' (needs review)' : ''}`}
                              >
                                {passport[col.key] || '—'}
                              </div>
                            )}
                          </td>
                        ))}

                        <td className="px-2 py-1 text-center" onClick={(e) => e.stopPropagation()}>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              deleteRow(index);
                            }}
                            className="text-red-500 hover:text-red-700 hover:bg-red-50 p-1 rounded transition"
                            title="Delete row"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Legend */}
            <div className="mt-3 flex items-center gap-4 text-xs text-gray-500 flex-wrap">
              <div className="flex items-center gap-1">
                <div className="w-3 h-3 bg-red-50 border border-red-200 rounded"></div>
                <span>Empty</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="w-3 h-3 bg-amber-100 border-l-2 border-l-amber-500 rounded"></div>
                <span>Needs review</span>
              </div>
              <div className="flex items-center gap-1">
                <div className="w-3 h-3 bg-blue-50 border-l-2 border-l-blue-500 rounded"></div>
                <span>Selected</span>
              </div>
            </div>
          </div>

          {/* Mobile table */}
          <div className="lg:hidden mb-6">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-200">
                      <th className="px-2 py-2 text-left text-xs font-semibold text-gray-600">#</th>
                      {columns.map((col) => (
                        <th key={col.key} className="px-2 py-2 text-left text-xs font-semibold text-gray-600">
                          {col.label}
                        </th>
                      ))}
                      <th className="px-2 py-2 text-center text-xs font-semibold text-gray-600">Del</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200">
                    {passports.map((passport, index) => (
                      <tr
                        key={index}
                        onClick={() => handleRowClick(index)}
                        className={`cursor-pointer ${selectedIndex === index ? 'bg-blue-50' : ''}`}
                      >
                        <td className="px-2 py-1 text-xs">{index + 1}</td>
                        {columns.map((col) => (
                          <td key={col.key} className={`px-2 py-1 text-xs ${nameFields.includes(col.key) ? 'uppercase' : ''} ${getCellStyle(passport, col.key)}`}>
                            {passport[col.key] || '—'}
                          </td>
                        ))}
                        <td className="px-2 py-1 text-center">
                          <button onClick={(e) => { e.stopPropagation(); deleteRow(index); }} className="text-red-500">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                            </svg>
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Draggable Divider */}
          <div
            className="hidden lg:flex items-center justify-center w-4 cursor-col-resize group hover:bg-blue-50 transition-colors"
            onMouseDown={handleMouseDown}
          >
            <div className={`w-1 h-16 rounded-full transition-colors ${isDragging ? 'bg-blue-500' : 'bg-gray-300 group-hover:bg-blue-400'}`}></div>
          </div>

          {/* Right: Image Preview Panel */}
          <div style={{ width: `${100 - leftPanelWidth - 1}%` }} className="hidden lg:block">
            <div className="lg:sticky lg:top-4">
              <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden ml-2">
                {/* Header with controls */}
                <div className="bg-gray-50 px-4 py-2 border-b border-gray-200">
                  <div className="flex justify-between items-center">
                    <h3 className="font-medium text-gray-700 text-sm">
                      Preview
                      {selectedPassport && (
                        <span className="text-gray-400 ml-2">
                          #{selectedIndex + 1}
                          {selectedPassport.confidence > 0 && (
                            <span className={`ml-2 ${selectedPassport.confidence >= 0.7 ? 'text-green-600' : 'text-amber-600'}`}>
                              ({Math.round(selectedPassport.confidence * 100)}% conf.)
                            </span>
                          )}
                        </span>
                      )}
                    </h3>

                    {/* Zoom & Rotate controls */}
                    <div className="flex items-center gap-2">
                      {/* Rotation controls */}
                      <div className="flex items-center gap-1 border-r border-gray-300 pr-2 mr-2">
                        <button
                          onClick={handleRotateLeft}
                          className="p-1 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded transition"
                          title="Rotate left"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
                          </svg>
                        </button>
                        <span className="text-xs text-gray-500 w-10 text-center font-mono">
                          {imageRotation % 360}°
                        </span>
                        <button
                          onClick={handleRotateRight}
                          className="p-1 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded transition"
                          title="Rotate right"
                        >
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 10h-10a8 8 0 00-8 8v2M21 10l-6 6m6-6l-6-6" />
                          </svg>
                        </button>
                        {imageRotation !== 0 && (
                          <button
                            onClick={handleRotateReset}
                            className="p-1 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded transition"
                            title="Reset rotation"
                          >
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                          </button>
                        )}
                      </div>

                      {/* Zoom controls */}
                      <button
                        onClick={handleZoomOut}
                        className="p-1 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded transition"
                        title="Zoom out"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
                        </svg>
                      </button>
                      <span className="text-xs text-gray-500 w-10 text-center font-mono">{zoom}%</span>
                      <button
                        onClick={handleZoomIn}
                        className="p-1 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded transition"
                        title="Zoom in"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                        </svg>
                      </button>
                      <button
                        onClick={handleZoomReset}
                        className="p-1 text-gray-500 hover:text-gray-700 hover:bg-gray-200 rounded transition"
                        title="Reset"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                        </svg>
                      </button>
                    </div>
                  </div>
                </div>

                {/* Image container */}
                <div
                  className="relative overflow-hidden bg-gray-100"
                  style={{ height: '400px' }}
                  onWheel={handleWheel}
                  onMouseDown={handlePanStart}
                  onMouseMove={handlePanMove}
                  onMouseUp={handlePanEnd}
                  onMouseLeave={handlePanEnd}
                >
                  {selectedPassport?.full_image ? (
                    <div
                      className={`absolute inset-0 flex items-center justify-center ${zoom > 100 ? 'cursor-grab' : ''} ${isPanning ? 'cursor-grabbing' : ''}`}
                      style={{
                        transform: `scale(${zoom / 100}) translate(${panPosition.x / (zoom / 100)}px, ${panPosition.y / (zoom / 100)}px)`,
                        transformOrigin: 'center center',
                      }}
                    >
                      <img
                        src={`data:image/jpeg;base64,${selectedPassport.full_image}`}
                        alt={`Passport ${selectedIndex + 1}`}
                        className="max-w-full max-h-full object-contain select-none"
                        style={{ transform: `rotate(${imageRotation}deg)` }}
                        draggable={false}
                      />
                    </div>
                  ) : selectedPassport?.thumbnail ? (
                    <div className="absolute inset-0 flex flex-col items-center justify-center">
                      <img
                        src={`data:image/jpeg;base64,${selectedPassport.thumbnail}`}
                        alt={`Passport ${selectedIndex + 1}`}
                        className="w-32 h-32 object-cover rounded border border-gray-200"
                        style={{ transform: `rotate(${imageRotation}deg)` }}
                      />
                      <p className="text-gray-400 text-sm mt-2">Thumbnail only</p>
                    </div>
                  ) : (
                    <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-400">
                      <svg className="w-16 h-16 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                      </svg>
                      <p className="text-sm">No image available</p>
                    </div>
                  )}

                  {selectedPassport?.full_image && zoom === 100 && (
                    <div className="absolute bottom-2 right-2 text-xs text-gray-400 bg-white/80 px-2 py-1 rounded">
                      Scroll to zoom
                    </div>
                  )}
                </div>

                {/* Passport info */}
                {selectedPassport && (
                  <div className="p-4 border-t border-gray-200">
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div>
                        <span className="text-gray-500">Name:</span>
                        <span className={`ml-1 font-medium uppercase ${isLowConfidence(selectedPassport, 'first_name') || isLowConfidence(selectedPassport, 'last_name') ? 'text-amber-600' : ''}`}>
                          {[selectedPassport.first_name, selectedPassport.middle_name, selectedPassport.last_name]
                            .filter(Boolean)
                            .join(' ') || '—'}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-500">Passport:</span>
                        <span className={`ml-1 font-medium ${isLowConfidence(selectedPassport, 'passport_number') ? 'text-amber-600' : ''}`}>
                          {selectedPassport.passport_number || '—'}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-500">DOB:</span>
                        <span className={`ml-1 font-medium ${isLowConfidence(selectedPassport, 'date_of_birth') ? 'text-amber-600' : ''}`}>
                          {selectedPassport.date_of_birth || '—'}
                        </span>
                      </div>
                      <div>
                        <span className="text-gray-500">Nationality:</span>
                        <span className={`ml-1 font-medium ${isLowConfidence(selectedPassport, 'nationality') ? 'text-amber-600' : ''}`}>
                          {selectedPassport.nationality || '—'}
                        </span>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Navigation buttons */}
              {passports.length > 1 && (
                <div className="flex justify-between mt-3 ml-2">
                  <button
                    onClick={() => setSelectedIndex(Math.max(0, selectedIndex - 1))}
                    disabled={selectedIndex === 0}
                    className="px-3 py-1 text-sm text-gray-600 bg-white border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => setSelectedIndex(Math.min(passports.length - 1, selectedIndex + 1))}
                    disabled={selectedIndex === passports.length - 1}
                    className="px-3 py-1 text-sm text-gray-600 bg-white border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Next
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Mobile: Image preview */}
          <div className="lg:hidden">
            <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
              <div className="bg-gray-50 px-4 py-2 border-b border-gray-200 flex justify-between items-center">
                <h3 className="font-medium text-gray-700 text-sm">Preview #{selectedIndex + 1}</h3>
                <div className="flex gap-1">
                  <button onClick={handleRotateLeft} className="p-1 text-gray-500">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
                    </svg>
                  </button>
                  <button onClick={handleRotateRight} className="p-1 text-gray-500">
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 10h-10a8 8 0 00-8 8v2M21 10l-6 6m6-6l-6-6" />
                    </svg>
                  </button>
                </div>
              </div>
              <div className="p-4">
                {selectedPassport?.full_image ? (
                  <img
                    src={`data:image/jpeg;base64,${selectedPassport.full_image}`}
                    alt={`Passport ${selectedIndex + 1}`}
                    className="w-full h-auto rounded border border-gray-200"
                    style={{ transform: `rotate(${imageRotation}deg)` }}
                  />
                ) : (
                  <div className="text-center text-gray-400 py-8">No image</div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default DataTable;
