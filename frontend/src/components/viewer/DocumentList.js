import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Container,
  Typography,
  Grid,
  Card,
  CardContent,
  CardActionArea,
  Box,
  Chip,
  CircularProgress,
  Alert,
  Button,
  TextField,
  InputAdornment,
  LinearProgress,
} from '@mui/material';
import {
  Description,
  Search,
  ArrowBack,
  CheckCircle,
  Error,
  Schedule,
  Chat,
} from '@mui/icons-material';
import { apiService } from '../../services/apiService';
import { format } from 'date-fns';

const DocumentList = () => {
  const { compound, studyId, deliverable } = useParams();
  const navigate = useNavigate();
  const [documents, setDocuments] = useState([]);
  const [filteredDocuments, setFilteredDocuments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    const fetchDocuments = async () => {
      try {
        setLoading(true);
        const response = await apiService.getDocumentsForDeliverable(compound, studyId, deliverable);
        setDocuments(response.documents || []);
        setFilteredDocuments(response.documents || []);
      } catch (err) {
        setError('Failed to load documents: ' + err.message);
        console.error('Error fetching documents:', err);
      } finally {
        setLoading(false);
      }
    };

    if (compound && studyId && deliverable) {
      fetchDocuments();
    }
  }, [compound, studyId, deliverable]);

  useEffect(() => {
    // Filter documents based on search term
    if (searchTerm) {
      const filtered = documents.filter(document =>
        document.filename.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (document.description && document.description.toLowerCase().includes(searchTerm.toLowerCase()))
      );
      setFilteredDocuments(filtered);
    } else {
      setFilteredDocuments(documents);
    }
  }, [searchTerm, documents]);

  const handleDocumentClick = (documentId) => {
    navigate(`/documents/${documentId}`);
  };

  const handleBackClick = () => {
    navigate(`/compounds/${encodeURIComponent(compound)}/studies/${encodeURIComponent(studyId)}/deliverables`);
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed': return 'success';
      case 'failed': return 'error';
      case 'processing': return 'warning';
      default: return 'default';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed': return <CheckCircle color="success" />;
      case 'failed': return <Error color="error" />;
      case 'processing': return <Schedule color="warning" />;
      default: return <Description />;
    }
  };

  if (loading) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4, textAlign: 'center' }}>
        <CircularProgress size={60} />
        <Typography variant="h6" sx={{ mt: 2 }}>
          Loading documents...
        </Typography>
      </Container>
    );
  }

  if (error) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4 }}>
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
        <Button startIcon={<ArrowBack />} onClick={handleBackClick}>
          Back to Deliverables
        </Button>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Button 
          startIcon={<ArrowBack />} 
          onClick={handleBackClick}
          sx={{ mb: 2 }}
        >
          Back to Deliverables
        </Button>
        
        <Typography variant="h4" component="h1" gutterBottom>
          Documents: {deliverable}
        </Typography>
        <Typography variant="body1" color="text.secondary" gutterBottom>
          {compound} • {studyId} • Click a document to view and chat
        </Typography>

        {/* Search Bar */}
        <TextField
          fullWidth
          variant="outlined"
          placeholder="Search documents..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          sx={{ mt: 2, mb: 3, maxWidth: 400 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Search />
              </InputAdornment>
            ),
          }}
        />
      </Box>

      {/* Summary Stats */}
      {documents.length > 0 && (
        <Box sx={{ mb: 4 }}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} md={3}>
              <Card variant="outlined">
                <CardContent sx={{ textAlign: 'center' }}>
                  <Description color="primary" sx={{ fontSize: 40, mb: 1 }} />
                  <Typography variant="h4" component="div">
                    {documents.length}
                  </Typography>
                  <Typography color="text.secondary">
                    Documents
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card variant="outlined">
                <CardContent sx={{ textAlign: 'center' }}>
                  <CheckCircle color="success" sx={{ fontSize: 40, mb: 1 }} />
                  <Typography variant="h4" component="div">
                    {documents.filter(d => d.status === 'completed').length}
                  </Typography>
                  <Typography color="text.secondary">
                    Completed
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card variant="outlined">
                <CardContent sx={{ textAlign: 'center' }}>
                  <Schedule color="warning" sx={{ fontSize: 40, mb: 1 }} />
                  <Typography variant="h4" component="div">
                    {documents.filter(d => d.status !== 'completed' && d.status !== 'failed').length}
                  </Typography>
                  <Typography color="text.secondary">
                    Processing
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card variant="outlined">
                <CardContent sx={{ textAlign: 'center' }}>
                  <Description color="secondary" sx={{ fontSize: 40, mb: 1 }} />
                  <Typography variant="h4" component="div">
                    {documents.reduce((total, doc) => total + (doc.tlf_outputs_found || 0), 0)}
                  </Typography>
                  <Typography color="text.secondary">
                    TLF Outputs
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Box>
      )}

      {/* Documents Grid */}
      {filteredDocuments.length === 0 ? (
        <Box sx={{ textAlign: 'center', mt: 4 }}>
          <Typography variant="h6" color="text.secondary">
            {searchTerm ? `No documents found matching "${searchTerm}"` : 'No documents available'}
          </Typography>
        </Box>
      ) : (
        <Grid container spacing={3}>
          {filteredDocuments.map((document) => (
            <Grid item xs={12} sm={6} md={6} key={document.document_id}>
              <Card 
                sx={{ 
                  height: '100%',
                  transition: 'transform 0.2s ease-in-out, box-shadow 0.2s ease-in-out',
                  '&:hover': {
                    transform: 'translateY(-2px)',
                    boxShadow: (theme) => theme.shadows[8],
                  },
                }}
              >
                <CardActionArea 
                  onClick={() => handleDocumentClick(document.document_id)}
                  sx={{ height: '100%', p: 0 }}
                  disabled={document.status !== 'completed'}
                >
                  <CardContent sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                    {/* Document Header */}
                    <Box sx={{ display: 'flex', alignItems: 'flex-start', mb: 2 }}>
                      {getStatusIcon(document.status)}
                      <Box sx={{ ml: 1, flexGrow: 1 }}>
                        <Typography variant="h6" component="div" sx={{ mb: 1 }}>
                          {document.filename}
                        </Typography>
                        <Chip 
                          label={document.status} 
                          size="small" 
                          color={getStatusColor(document.status)}
                          variant="outlined"
                        />
                      </Box>
                    </Box>

                    {/* Description */}
                    {document.description && (
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                        {document.description}
                      </Typography>
                    )}

                    {/* Document Stats */}
                    <Box sx={{ mb: 2 }}>
                      <Grid container spacing={1}>
                        <Grid item xs={4}>
                          <Typography variant="body2" color="text.secondary">
                            Pages
                          </Typography>
                          <Typography variant="body1" fontWeight="medium">
                            {document.total_pages || 'N/A'}
                          </Typography>
                        </Grid>
                        <Grid item xs={4}>
                          <Typography variant="body2" color="text.secondary">
                            Chunks
                          </Typography>
                          <Typography variant="body1" fontWeight="medium">
                            {document.total_chunks || 0}
                          </Typography>
                        </Grid>
                        <Grid item xs={4}>
                          <Typography variant="body2" color="text.secondary">
                            TLF Outputs
                          </Typography>
                          <Typography variant="body1" fontWeight="medium" color="primary">
                            {document.tlf_outputs_found || 0}
                          </Typography>
                        </Grid>
                      </Grid>
                    </Box>

                    {/* Processing Progress */}
                    {document.status === 'processing' && (
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="body2" color="text.secondary" gutterBottom>
                          Processing...
                        </Typography>
                        <LinearProgress variant="indeterminate" />
                      </Box>
                    )}

                    {/* Error Message */}
                    {document.status === 'failed' && (
                      <Alert severity="error" sx={{ mb: 2 }}>
                        Processing failed
                      </Alert>
                    )}

                    {/* TLF Distribution */}
                    {document.tlf_types_distribution && Object.keys(document.tlf_types_distribution).length > 0 && (
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="body2" color="text.secondary" gutterBottom>
                          TLF Types:
                        </Typography>
                        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                          {Object.entries(document.tlf_types_distribution).map(([type, count]) => (
                            <Chip
                              key={type}
                              label={`${type}: ${count}`}
                              size="small"
                              variant="outlined"
                              color="primary"
                            />
                          ))}
                        </Box>
                      </Box>
                    )}

                    {/* Clinical Domains */}
                    {document.clinical_domains_distribution && Object.keys(document.clinical_domains_distribution).length > 0 && (
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="body2" color="text.secondary" gutterBottom>
                          Clinical Domains:
                        </Typography>
                        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                          {Object.entries(document.clinical_domains_distribution).slice(0, 3).map(([domain, count]) => (
                            <Chip
                              key={domain}
                              label={domain.replace('_', ' ')}
                              size="small"
                              variant="outlined"
                              color="secondary"
                            />
                          ))}
                          {Object.keys(document.clinical_domains_distribution).length > 3 && (
                            <Chip
                              label={`+${Object.keys(document.clinical_domains_distribution).length - 3} more`}
                              size="small"
                              variant="outlined"
                              color="default"
                            />
                          )}
                        </Box>
                      </Box>
                    )}

                    {/* Footer */}
                    <Box sx={{ mt: 'auto', pt: 2, borderTop: 1, borderColor: 'divider' }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Typography variant="caption" color="text.secondary">
                          {document.created_at ? 
                            format(new Date(document.created_at), 'MMM dd, yyyy HH:mm') : 
                            'Unknown date'
                          }
                        </Typography>
                        
                        {document.status === 'completed' && (
                          <Box sx={{ display: 'flex', alignItems: 'center' }}>
                            <Chat fontSize="small" color="primary" sx={{ mr: 0.5 }} />
                            <Typography variant="caption" color="primary">
                              Ready to chat
                            </Typography>
                          </Box>
                        )}
                      </Box>
                    </Box>
                  </CardContent>
                </CardActionArea>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}
    </Container>
  );
};

export default DocumentList;
