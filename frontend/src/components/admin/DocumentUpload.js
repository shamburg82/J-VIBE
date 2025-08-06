import React, { useState, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Container,
  Typography,
  Box,
  Paper,
  TextField,
  Button,
  LinearProgress,
  Alert,
  Card,
  CardContent,
  List,
  ListItem,
  ListItemText,
  ListItemIcon,
  IconButton,
  Chip,
  Grid,
  Divider,
} from '@mui/material';
import {
  CloudUpload,
  InsertDriveFile,
  Delete,
  CheckCircle,
  Error,
  Schedule,
  ArrowBack,
} from '@mui/icons-material';
import { apiService } from '../../services/apiService';

const DocumentUpload = () => {
  const navigate = useNavigate();
  const fileInputRef = useRef(null);
  
  // Form state
  const [compound, setCompound] = useState('');
  const [studyId, setStudyId] = useState('');
  const [deliverable, setDeliverable] = useState('');
  const [description, setDescription] = useState('');
  
  // File and upload state
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [uploads, setUploads] = useState({}); // documentId -> upload info
  const [isDragOver, setIsDragOver] = useState(false);
  const [error, setError] = useState(null);

  // Drag and drop handlers
  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setIsDragOver(false);
    
    const files = Array.from(e.dataTransfer.files);
    handleFileSelection(files);
  }, []);

  const handleFileSelection = (files) => {
    const pdfFiles = files.filter(file => file.type === 'application/pdf');
    
    if (pdfFiles.length !== files.length) {
      setError('Only PDF files are supported');
      return;
    }

    if (pdfFiles.length > 10) {
      setError('Maximum 10 files can be uploaded at once');
      return;
    }

    const fileObjects = pdfFiles.map(file => ({
      id: Date.now() + Math.random(),
      file,
      name: file.name,
      size: file.size,
      status: 'pending'
    }));

    setSelectedFiles(prev => [...prev, ...fileObjects]);
    setError(null);
  };

  const handleFileInputChange = (e) => {
    if (e.target.files) {
      handleFileSelection(Array.from(e.target.files));
    }
  };

  const handleRemoveFile = (fileId) => {
    setSelectedFiles(prev => prev.filter(f => f.id !== fileId));
  };

  const validateForm = () => {
    if (!compound.trim()) {
      setError('Compound is required');
      return false;
    }
    if (!studyId.trim()) {
      setError('Study ID is required');
      return false;
    }
    if (!deliverable.trim()) {
      setError('Deliverable is required');
      return false;
    }
    if (selectedFiles.length === 0) {
      setError('At least one file must be selected');
      return false;
    }
    return true;
  };

  const startUpload = async (fileObj) => {
    try {
      const formData = new FormData();
      formData.append('file', fileObj.file);
      formData.append('compound', compound.trim());
      formData.append('study_id', studyId.trim());
      formData.append('deliverable', deliverable.trim());
      if (description.trim()) {
        formData.append('description', description.trim());
      }

      // Start upload with progress tracking
      const uploadResponse = await apiService.uploadDocument(
        formData,
        (progressPercent) => {
          setUploads(prev => ({
            ...prev,
            [fileObj.id]: {
              ...prev[fileObj.id],
              uploadProgress: progressPercent
            }
          }));
        }
      );

      const documentId = uploadResponse.document_id;
      
      // Initialize upload tracking
      setUploads(prev => ({
        ...prev,
        [fileObj.id]: {
          documentId,
          status: 'uploaded',
          uploadProgress: 100,
          processingProgress: uploadResponse.progress || 0,
          message: uploadResponse.message || 'Processing...',
          filename: fileObj.name
        }
      }));

      // Start processing status monitoring
      monitorProcessingStatus(fileObj.id, documentId);

    } catch (err) {
      console.error('Upload error:', err);
      setUploads(prev => ({
        ...prev,
        [fileObj.id]: {
          ...prev[fileObj.id],
          status: 'error',
          error: err.message
        }
      }));
    }
  };

  const monitorProcessingStatus = async (fileId, documentId) => {
    try {
      // Use Server-Sent Events for real-time updates
      const eventSource = apiService.createStatusStream(documentId);

      eventSource.onmessage = (event) => {
        try {
          const statusData = JSON.parse(event.data);
          
          setUploads(prev => ({
            ...prev,
            [fileId]: {
              ...prev[fileId],
              processingProgress: statusData.progress || 0,
              message: statusData.message || 'Processing...',
              status: statusData.status === 'completed' ? 'completed' : 
                     statusData.status === 'failed' ? 'error' : 'processing',
              error: statusData.error_message || null,
              tlf_outputs_found: statusData.tlf_outputs_found || 0
            }
          }));

          // Close stream when processing is complete
          if (statusData.status === 'completed' || statusData.status === 'failed') {
            eventSource.close();
          }

        } catch (parseError) {
          console.error('Failed to parse status update:', parseError);
        }
      };

      eventSource.onerror = (error) => {
        console.error('EventSource error:', error);
        eventSource.close();
        
        // Fallback to polling
        setTimeout(() => pollProcessingStatus(fileId, documentId), 2000);
      };

    } catch (err) {
      console.error('Monitoring setup error:', err);
      // Fallback to polling
      pollProcessingStatus(fileId, documentId);
    }
  };

  const pollProcessingStatus = async (fileId, documentId) => {
    try {
      const status = await apiService.getProcessingStatus(documentId);
      
      if (status) {
        setUploads(prev => ({
          ...prev,
          [fileId]: {
            ...prev[fileId],
            processingProgress: status.progress || 0,
            message: status.message || 'Processing...',
            status: status.status === 'completed' ? 'completed' : 
                   status.status === 'failed' ? 'error' : 'processing',
            error: status.error_message || null,
            tlf_outputs_found: status.tlf_outputs_found || 0
          }
        }));

        // Continue polling if still processing
        if (status.status !== 'completed' && status.status !== 'failed') {
          setTimeout(() => pollProcessingStatus(fileId, documentId), 3000);
        }
      }
    } catch (err) {
      console.error('Polling error:', err);
      // Retry polling after delay
      setTimeout(() => pollProcessingStatus(fileId, documentId), 5000);
    }
  };

  const handleUploadAll = async () => {
    if (!validateForm()) return;

    setError(null);
    
    // Start uploads for all pending files
    const pendingFiles = selectedFiles.filter(f => !uploads[f.id] || uploads[f.id].status === 'pending');
    
    for (const fileObj of pendingFiles) {
      setUploads(prev => ({
        ...prev,
        [fileObj.id]: {
          status: 'uploading',
          uploadProgress: 0,
          processingProgress: 0,
          filename: fileObj.name
        }
      }));
      
      // Start upload (async - don't wait)
      startUpload(fileObj);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed': return 'success';
      case 'error': return 'error';
      case 'uploading':
      case 'processing': return 'warning';
      default: return 'default';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed': return <CheckCircle color="success" />;
      case 'error': return <Error color="error" />;
      case 'uploading':
      case 'processing': return <Schedule color="warning" />;
      default: return <InsertDriveFile />;
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const hasActiveUploads = Object.values(uploads).some(
    upload => upload.status === 'uploading' || upload.status === 'processing'
  );

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Button 
          startIcon={<ArrowBack />} 
          onClick={() => navigate('/admin')}
          sx={{ mb: 2 }}
        >
          Back to Dashboard
        </Button>
        
        <Typography variant="h4" component="h1" gutterBottom>
          Upload Documents
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Upload TLF documents for processing and analysis
        </Typography>
      </Box>

      <Grid container spacing={3}>
        {/* Upload Form */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Document Information
            </Typography>

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <TextField
                label="Compound *"
                value={compound}
                onChange={(e) => setCompound(e.target.value)}
                placeholder="e.g., JZP123"
                fullWidth
                disabled={hasActiveUploads}
              />

              <TextField
                label="Study ID *"
                value={studyId}
                onChange={(e) => setStudyId(e.target.value)}
                placeholder="e.g., JZP123-001"
                fullWidth
                disabled={hasActiveUploads}
              />

              <TextField
                label="Deliverable *"
                value={deliverable}
                onChange={(e) => setDeliverable(e.target.value)}
                placeholder="e.g., Final CSR, Interim Analysis 1"
                fullWidth
                disabled={hasActiveUploads}
              />

              <TextField
                label="Description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Optional description"
                multiline
                rows={3}
                fullWidth
                disabled={hasActiveUploads}
              />
            </Box>
          </Paper>

          {/* File Drop Zone */}
          <Paper 
            sx={{ 
              p: 4, 
              mt: 3,
              border: 2, 
              borderStyle: 'dashed',
              borderColor: isDragOver ? 'primary.main' : 'grey.300',
              bgcolor: isDragOver ? 'action.hover' : 'background.paper',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              textAlign: 'center'
            }}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <CloudUpload 
              color={isDragOver ? 'primary' : 'action'} 
              sx={{ fontSize: 48, mb: 2 }} 
            />
            <Typography variant="h6" gutterBottom>
              {isDragOver ? 'Drop files here' : 'Drop PDF files or click to browse'}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Support for PDF files up to 50MB each. Maximum 10 files at once.
            </Typography>
            
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              multiple
              onChange={handleFileInputChange}
              style={{ display: 'none' }}
            />
          </Paper>

          {/* Upload Button */}
          <Box sx={{ mt: 3, textAlign: 'center' }}>
            <Button
              variant="contained"
              size="large"
              onClick={handleUploadAll}
              disabled={selectedFiles.length === 0 || hasActiveUploads || !compound || !studyId || !deliverable}
              startIcon={<CloudUpload />}
            >
              Upload {selectedFiles.length} File{selectedFiles.length !== 1 ? 's' : ''}
            </Button>
          </Box>
        </Grid>

        {/* File List and Progress */}
        <Grid item xs={12} md={6}>
          <Paper sx={{ p: 3 }}>
            <Typography variant="h6" gutterBottom>
              Selected Files ({selectedFiles.length})
            </Typography>

            {error && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {error}
              </Alert>
            )}

            {selectedFiles.length === 0 ? (
              <Box sx={{ textAlign: 'center', py: 4 }}>
                <InsertDriveFile color="disabled" sx={{ fontSize: 48, mb: 2 }} />
                <Typography color="text.secondary">
                  No files selected
                </Typography>
              </Box>
            ) : (
              <List>
                {selectedFiles.map((fileObj, index) => {
                  const upload = uploads[fileObj.id];
                  
                  return (
                    <React.Fragment key={fileObj.id}>
                      <ListItem sx={{ px: 0 }}>
                        <ListItemIcon>
                          {getStatusIcon(upload?.status || 'pending')}
                        </ListItemIcon>
                        
                        <ListItemText
                          primary={
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                              <Typography variant="body2" noWrap>
                                {fileObj.name}
                              </Typography>
                              <Chip 
                                label={upload?.status || 'pending'} 
                                size="small" 
                                color={getStatusColor(upload?.status || 'pending')}
                                variant="outlined"
                              />
                            </Box>
                          }
                          secondary={
                            <Box>
                              <Typography variant="caption" color="text.secondary">
                                {formatFileSize(fileObj.size)}
                              </Typography>
                              
                              {upload?.message && (
                                <Typography variant="caption" display="block">
                                  {upload.message}
                                </Typography>
                              )}
                              
                              {upload?.error && (
                                <Typography variant="caption" color="error" display="block">
                                  Error: {upload.error}
                                </Typography>
                              )}
                              
                              {upload?.tlf_outputs_found > 0 && (
                                <Typography variant="caption" color="success.main" display="block">
                                  Found {upload.tlf_outputs_found} TLF outputs
                                </Typography>
                              )}
                            </Box>
                          }
                        />

                        {!upload?.status || upload.status === 'pending' ? (
                          <IconButton 
                            onClick={() => handleRemoveFile(fileObj.id)}
                            color="error"
                            size="small"
                          >
                            <Delete />
                          </IconButton>
                        ) : (
                          <Box sx={{ minWidth: 100 }}>
                            {upload.status === 'uploading' && (
                              <Box>
                                <Typography variant="caption" color="text.secondary">
                                  Uploading: {upload.uploadProgress}%
                                </Typography>
                                <LinearProgress 
                                  variant="determinate" 
                                  value={upload.uploadProgress} 
                                  sx={{ mt: 0.5 }}
                                />
                              </Box>
                            )}
                            
                            {upload.status === 'processing' && (
                              <Box>
                                <Typography variant="caption" color="text.secondary">
                                  Processing: {upload.processingProgress}%
                                </Typography>
                                <LinearProgress 
                                  variant="determinate" 
                                  value={upload.processingProgress} 
                                  sx={{ mt: 0.5 }}
                                />
                              </Box>
                            )}
                            
                            {upload.status === 'completed' && upload.documentId && (
                              <Button
                                size="small"
                                variant="outlined"
                                onClick={() => navigate(`/documents/${upload.documentId}`)}
                              >
                                View
                              </Button>
                            )}
                          </Box>
                        )}
                      </ListItem>
                      
                      {index < selectedFiles.length - 1 && <Divider />}
                    </React.Fragment>
                  );
                })}
              </List>
            )}
          </Paper>
        </Grid>
      </Grid>
    </Container>
  );
};

export default DocumentUpload;
