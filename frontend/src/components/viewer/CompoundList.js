import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
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
  TextField,
  InputAdornment,
} from '@mui/material';
import {
  Science,
  Search,
  Assignment,
  Description,
} from '@mui/icons-material';
import { apiService } from '../../services/apiService';

const CompoundList = () => {
  const navigate = useNavigate();
  const [compounds, setCompounds] = useState([]);
  const [filteredCompounds, setFilteredCompounds] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    const fetchCompounds = async () => {
      try {
        setLoading(true);
        const response = await apiService.getCompounds();
        setCompounds(response.compound_details || []);
        setFilteredCompounds(response.compound_details || []);
      } catch (err) {
        setError('Failed to load compounds: ' + err.message);
        console.error('Error fetching compounds:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchCompounds();
  }, []);

  useEffect(() => {
    // Filter compounds based on search term
    if (searchTerm) {
      const filtered = compounds.filter(compound =>
        compound.compound.toLowerCase().includes(searchTerm.toLowerCase())
      );
      setFilteredCompounds(filtered);
    } else {
      setFilteredCompounds(compounds);
    }
  }, [searchTerm, compounds]);

  const handleCompoundClick = (compound) => {
    navigate(`/compounds/${encodeURIComponent(compound)}/studies`);
  };

  if (loading) {
    return (
      <Container maxWidth="lg" sx={{ mt: 4, textAlign: 'center' }}>
        <CircularProgress size={60} />
        <Typography variant="h6" sx={{ mt: 2 }}>
          Loading compounds...
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
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ mt: 4, mb: 4 }}>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Clinical Trial Compounds
        </Typography>
        <Typography variant="body1" color="text.secondary" gutterBottom>
          Select a compound to explore its clinical studies and TLF documents
        </Typography>

        {/* Search Bar */}
        <TextField
          fullWidth
          variant="outlined"
          placeholder="Search compounds..."
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
      {compounds.length > 0 && (
        <Box sx={{ mb: 4 }}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6} md={3}>
              <Card variant="outlined">
                <CardContent sx={{ textAlign: 'center' }}>
                  <Science color="primary" sx={{ fontSize: 40, mb: 1 }} />
                  <Typography variant="h4" component="div">
                    {compounds.length}
                  </Typography>
                  <Typography color="text.secondary">
                    Compounds
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card variant="outlined">
                <CardContent sx={{ textAlign: 'center' }}>
                  <Assignment color="primary" sx={{ fontSize: 40, mb: 1 }} />
                  <Typography variant="h4" component="div">
                    {compounds.reduce((total, compound) => total + compound.study_count, 0)}
                  </Typography>
                  <Typography color="text.secondary">
                    Studies
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card variant="outlined">
                <CardContent sx={{ textAlign: 'center' }}>
                  <Description color="primary" sx={{ fontSize: 40, mb: 1 }} />
                  <Typography variant="h4" component="div">
                    {compounds.reduce((total, compound) => total + compound.deliverable_count, 0)}
                  </Typography>
                  <Typography color="text.secondary">
                    Deliverables
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid item xs={12} sm={6} md={3}>
              <Card variant="outlined">
                <CardContent sx={{ textAlign: 'center' }}>
                  <Description color="secondary" sx={{ fontSize: 40, mb: 1 }} />
                  <Typography variant="h4" component="div">
                    {compounds.reduce((total, compound) => total + compound.document_count, 0)}
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

      {/* Compounds Grid */}
      {filteredCompounds.length === 0 ? (
        <Box sx={{ textAlign: 'center', mt: 4 }}>
          <Typography variant="h6" color="text.secondary">
            {searchTerm ? `No compounds found matching "${searchTerm}"` : 'No compounds available'}
          </Typography>
        </Box>
      ) : (
        <Grid container spacing={3}>
          {filteredCompounds.map((compound) => (
            <Grid item xs={12} sm={6} md={4} key={compound.compound}>
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
                  onClick={() => handleCompoundClick(compound.compound)}
                  sx={{ height: '100%', p: 0 }}
                >
                  <CardContent sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                    {/* Compound Name */}
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                      <Science color="primary" sx={{ mr: 1 }} />
                      <Typography variant="h6" component="div" noWrap>
                        {compound.compound}
                      </Typography>
                    </Box>

                    {/* Stats */}
                    <Box sx={{ mb: 2, flexGrow: 1 }}>
                      <Grid container spacing={1}>
                        <Grid item xs={6}>
                          <Typography variant="body2" color="text.secondary">
                            Studies
                          </Typography>
                          <Typography variant="h6" color="primary">
                            {compound.study_count}
                          </Typography>
                        </Grid>
                        <Grid item xs={6}>
                          <Typography variant="body2" color="text.secondary">
                            Documents
                          </Typography>
                          <Typography variant="h6" color="primary">
                            {compound.document_count}
                          </Typography>
                        </Grid>
                      </Grid>
                    </Box>

                    {/* Study List */}
                    <Box sx={{ mb: 2 }}>
                      <Typography variant="body2" color="text.secondary" gutterBottom>
                        Studies:
                      </Typography>
                      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                        {compound.studies.slice(0, 3).map((study) => (
                          <Chip
                            key={study}
                            label={study}
                            size="small"
                            variant="outlined"
                            color="primary"
                          />
                        ))}
                        {compound.studies.length > 3 && (
                          <Chip
                            label={`+${compound.studies.length - 3} more`}
                            size="small"
                            variant="outlined"
                            color="default"
                          />
                        )}
                      </Box>
                    </Box>

                    {/* Deliverable Count */}
                    <Box sx={{ mt: 'auto' }}>
                      <Typography variant="caption" color="text.secondary">
                        {compound.deliverable_count} deliverable{compound.deliverable_count !== 1 ? 's' : ''}
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

export default CompoundList;
