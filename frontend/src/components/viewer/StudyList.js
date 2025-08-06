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
  Assignment,
  Search,
  ArrowBack,
  Description,
} from '@mui/icons-material';
import { apiService } from '../../services/apiService';

const StudyList = () => {
  const { compound } = useParams();
  const navigate = useNavigate();
  const [studies, setStudies] = useState([]);
  const [filteredStudies, setFilteredStudies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    const fetchStudies = async () => {
      try {
        setLoading(true);
        const response = await apiService.getStudiesForCompound(compound);
        setStudies(response.study_details || []);
        setFilteredStudies(response.study_details || []);
      } catch (err) {
        setError('Failed to load studies: ' + err.message);
        console.error('Error fetching studies:', err);
      } finally {
        setLoading(false);
      }
    };

    if (compound) {
      fetchStudies();
    }
  }, [compound]);

  useEffect(() => {
    // Filter studies based on search term
    if (searchTerm) {
      const filtered = studies.filter(study =>
        study.study_id.toLowerCase().includes(searchTerm.toLowerCase())
      );
      setFilteredStudies(filtered);
    } else {
      setFilteredStudies(studies);
    }
  }, [searchTerm, studies]);

  const handleStudyClick = (studyId) => {
    navigate(`/compounds/${encodeURIComponent(compound)}/studies/${encodeURIComponent(studyId)}/deliverables`);
  };

  const handleBackClick = () => {
    navigate('/compounds');
  };

  if (loading) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4, textAlign: 'center' }}>
        <CircularProgress size={60} />
        <Typography variant="h6" sx={{ mt: 2 }}>
          Loading studies...
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
          Back to Compounds
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
          Back to Compounds
        </Button>
        
        <Typography variant="h4" component="h1" gutterBottom>
          Studies for {compound}
        </Typography>
        <Typography variant="body1" color="text.secondary" gutterBottom>
          Select a study to explore its deliverables and documents
        </Typography>

        {/* Search Bar */}
        <TextField
          fullWidth
          variant="outlined"
          placeholder="Search studies..."
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
      {studies.length > 0 && (
        <Box sx={{ mb: 4 }}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} md={4}>
              <Card variant="outlined">
                <CardContent sx={{ textAlign: 'center' }}>
                  <Assignment color="primary" sx={{ fontSize: 40, mb: 1 }} />
                  <Typography variant="h4" component="div">
                    {studies.length}
                  </Typography>
                  <Typography color="text.secondary">
                    Studies
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={4}>
              <Card variant="outlined">
                <CardContent sx={{ textAlign: 'center' }}>
                  <Description color="primary" sx={{ fontSize: 40, mb: 1 }} />
                  <Typography variant="h4" component="div">
                    {studies.reduce((total, study) => total + study.deliverable_count, 0)}
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
                    {studies.reduce((total, study) => total + study.document_count, 0)}
                  </Typography>
                  <Typography color="text.secondary">
                    Documents
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          </Grid>
        </Box>
      )}

      {/* Studies Grid */}
      {filteredStudies.length === 0 ? (
        <Box sx={{ textAlign: 'center', mt: 4 }}>
          <Typography variant="h6" color="text.secondary">
            {searchTerm ? `No studies found matching "${searchTerm}"` : 'No studies available'}
          </Typography>
        </Box>
      ) : (
        <Grid container spacing={3}>
          {filteredStudies.map((study) => (
            <Grid item xs={12} sm={6} md={4} key={study.study_id}>
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
                  onClick={() => handleStudyClick(study.study_id)}
                  sx={{ height: '100%', p: 0 }}
                >
                  <CardContent sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                    {/* Study ID */}
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                      <Assignment color="primary" sx={{ mr: 1 }} />
                      <Typography variant="h6" component="div" noWrap>
                        {study.study_id}
                      </Typography>
                    </Box>

                    {/* Stats */}
                    <Box sx={{ mb: 2, flexGrow: 1 }}>
                      <Grid container spacing={1}>
                        <Grid item xs={6}>
                          <Typography variant="body2" color="text.secondary">
                            Deliverables
                          </Typography>
                          <Typography variant="h6" color="primary">
                            {study.deliverable_count}
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="body2" color="text.secondary">
                            Documents
                          </Typography>
                          <Typography variant="h6" color="primary">
                            {study.document_count}
                          </Typography>
                        </Grid>
                      </Grid>
                    </Box>

                    {/* Deliverable List */}
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="body2" color="text.secondary" gutterBottom>
                        Deliverables:
                      </Typography>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {study.deliverables.slice(0, 3).map((deliverable) => (
                          <Chip
                            key={deliverable}
                            label={deliverable}
                            size="small"
                            variant="outlined"
                            color="primary"
                            sx={{ fontSize: '0.7rem' }}
                          />
                        ))}
                        {study.deliverables.length > 3 && (
                          <Chip
                            label={`+${study.deliverables.length - 3} more`}
                            size="small"
                            variant="outlined"
                            color="default"
                            sx={{ fontSize: '0.7rem' }}
                          />
                        )}
                      </Box>
                    </Box>

                    {/* Footer Info */}
                    <Box sx={{ mt: 'auto', pt: 1, borderTop: 1, borderColor: 'divider' }}>
                      <Typography variant="caption" color="text.secondary">
                        Click to view deliverables
                      </Typography>
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

export default StudyList;
