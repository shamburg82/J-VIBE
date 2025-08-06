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
} from '@mui/material';
import {
  Description,
  Search,
  ArrowBack,
  Schedule,
} from '@mui/icons-material';
import { apiService } from '../../services/apiService';
import { format } from 'date-fns';

const DeliverableList = () => {
  const { compound, studyId } = useParams();
  const navigate = useNavigate();
  const [deliverables, setDeliverables] = useState([]);
  const [filteredDeliverables, setFilteredDeliverables] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    const fetchDeliverables = async () => {
      try {
        setLoading(true);
        const response = await apiService.getDeliverablesForStudy(compound, studyId);
        setDeliverables(response.deliverable_details || []);
        setFilteredDeliverables(response.deliverable_details || []);
      } catch (err) {
        setError('Failed to load deliverables: ' + err.message);
        console.error('Error fetching deliverables:', err);
      } finally {
        setLoading(false);
      }
    };

    if (compound && studyId) {
      fetchDeliverables();
    }
  }, [compound, studyId]);

  useEffect(() => {
    // Filter deliverables based on search term
    if (searchTerm) {
      const filtered = deliverables.filter(deliverable =>
        deliverable.deliverable.toLowerCase().includes(searchTerm.toLowerCase())
      );
      setFilteredDeliverables(filtered);
    } else {
      setFilteredDeliverables(deliverables);
    }
  }, [searchTerm, deliverables]);

  const handleDeliverableClick = (deliverable) => {
    navigate(
      `/compounds/${encodeURIComponent(compound)}/studies/${encodeURIComponent(studyId)}/deliverables/${encodeURIComponent(deliverable)}/documents`
    );
  };

  const handleBackClick = () => {
    navigate(`/compounds/${encodeURIComponent(compound)}/studies`);
  };

  if (loading) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4, textAlign: 'center' }}>
        <CircularProgress size={60} />
        <Typography variant="h6" sx={{ mt: 2 }}>
          Loading deliverables...
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
          Back to Studies
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
          Back to Studies
        </Button>
        
        <Typography variant="h4" component="h1" gutterBottom>
          Deliverables for {studyId}
        </Typography>
        <Typography variant="body1" color="text.secondary" gutterBottom>
          Compound: {compound} • Select a deliverable to view documents
        </Typography>

        {/* Search Bar */}
        <TextField
          fullWidth
          variant="outlined"
          placeholder="Search deliverables..."
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
      {deliverables.length > 0 && (
        <Box sx={{ mb: 4 }}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} md={4}>
              <Card variant="outlined">
                <CardContent sx={{ textAlign: 'center' }}>
                  <Description color="primary" sx={{ fontSize: 40, mb: 1 }} />
                  <Typography variant="h4" component="div">
                    {deliverables.length}
                  </Typography>
                  <Typography color="text.secondary">
                    Deliverables
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={4}>
              <Card variant="outlined">
                <CardContent sx={{ textAlign: 'center' }}>
                  <Description color="secondary" sx={{ fontSize: 40, mb: 1 }} />
                  <Typography variant="h4" component="div">
                    {deliverables.reduce((total, deliverable) => total + deliverable.document_count, 0)}
                  </Typography>
                  <Typography color="text.secondary">
                    Documents
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={4}>
              <Card variant="outlined">
                <CardContent sx={{ textAlign: 'center' }}>
                  <Schedule color="primary" sx={{ fontSize: 40, mb: 1 }} />
                  <Typography variant="h4" component="div">
                    {deliverables.length > 0 ? 
                      format(new Date(Math.max(...deliverables.map(d => new Date(d.latest_upload || 0)))), 'MMM dd') : 
                      'N/A'
                    }
                  </Typography>
                  <Typography color="text.secondary">
                    Latest Upload
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Box>
      )}

      {/* Deliverables Grid */}
      {filteredDeliverables.length === 0 ? (
        <Box sx={{ textAlign: 'center', mt: 4 }}>
          <Typography variant="h6" color="text.secondary">
            {searchTerm ? `No deliverables found matching "${searchTerm}"` : 'No deliverables available'}
          </Typography>
        </Box>
      ) : (
        <Grid container spacing={3}>
          {filteredDeliverables.map((deliverable) => (
            <Grid item xs={12} sm={6} md={4} key={deliverable.deliverable}>
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
                  onClick={() => handleDeliverableClick(deliverable.deliverable)}
                  sx={{ height: '100%', p: 0 }}
                >
                  <CardContent sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                    {/* Deliverable Name */}
                    <Box sx={{ display: 'flex', alignItems: 'flex-start', mb: 2 }}>
                      <Description color="primary" sx={{ mr: 1, mt: 0.5 }} />
                      <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
                        {deliverable.deliverable}
                      </Typography>
                    </Box>

                    {/* Document Count */}
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="h4" color="primary" gutterBottom>
                        {deliverable.document_count}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Document{deliverable.document_count !== 1 ? 's' : ''}
                      </Typography>
                    </Box>

                    {/* Latest Upload Info */}
                    {deliverable.latest_upload && (
                      <Box sx={{ mb: 2, flexGrow: 1 }}>
                        <Typography variant="body2" color="text.secondary" gutterBottom>
                          Latest Upload:
                        </Typography>
                        <Typography variant="body2">
                          {format(new Date(deliverable.latest_upload), 'MMM dd, yyyy HH:mm')}
                        </Typography>
                      </Box>
                    )}

                    {/* Documents Preview */}
                    {deliverable.documents && deliverable.documents.length > 0 && (
                      <Box sx={{ mb: 2 }}>
                        <Typography variant="body2" color="text.secondary" gutterBottom>
                          Documents:
                        </Typography>
                        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                          {deliverable.documents.slice(0, 2).map((doc, idx) => (
                            <Typography 
                              key={idx} 
                              variant="caption" 
                              sx={{ 
                                display: 'block',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap'
                              }}
                            >
                              • {doc.filename || 'Document'}
                            </Typography>
                          ))}
                          {deliverable.documents.length > 2 && (
                            <Typography variant="caption" color="text.secondary">
                              +{deliverable.documents.length - 2} more
                            </Typography>
                          )}
                        </Box>
                      </Box>
                    )}

                    {/* Status Indicators */}
                    <Box sx={{ mt: 'auto', pt: 1, borderTop: 1, borderColor: 'divider' }}>
                      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <Typography variant="caption" color="text.secondary">
                          Click to view documents
                        </Typography>
                        
                        {deliverable.documents && deliverable.documents.some(doc => doc.status === 'completed') && (
                          <Chip 
                            label="Ready" 
                            size="small" 
                            color="success" 
                            variant="outlined"
                          />
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

export default DeliverableList;
