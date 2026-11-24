/* eslint-disable react/prop-types */
import React, { forwardRef, useContext, useEffect, useRef, useState } from 'react';
import { Accordion, AccordionSummary, AccordionDetails, Autocomplete, Typography, TextField, Box, Checkbox, FormControlLabel, IconButton, Divider, Alert, Button } from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import NameContext from '../../context/NameContext';
import { patchPart, numberInstances } from '../../utils/Draft.js';
import DeleteIcon from '@mui/icons-material/Delete';
import { FixedSizeList } from 'react-window';

const PredictionAccordion = ({ item, index, setPrediction, helperText, setErrors, API_BASE_URL }) => {
  const { namesCache, roles } = useContext(NameContext);
  const checkedAddComponent = Boolean(item.new);
  const [lookupError, setLookupError] = useState(false);
  const requestGeneration = useRef(0);
  const abortLookup = useRef(null);
  useEffect(() => () => {
    requestGeneration.current += 1;
    abortLookup.current?.abort();
  }, []);

  const cancelLookup = () => {
    requestGeneration.current += 1;
    abortLookup.current?.abort();
    setLookupError(false);
  };
  const patch = values => setPrediction(current => patchPart(current, item.id, values));

  const handleRoleChange = (event, newValue) => {
    cancelLookup();
    patch({ role: newValue || '', name: '', identifier: '', description: '', sequence: '', sequence_length: '' });
  };

  const loadDetails = async (name) => {
    cancelLookup();
    if (!name) return;
    const generation = requestGeneration.current;
    const controller = new AbortController();
    abortLookup.current = controller;
    const role = item.role;
    try {
      const query = new URLSearchParams({ component_name: name, role });
      const response = await fetch(`${API_BASE_URL}/component/details?${query}`, { signal: controller.signal });
      if (!response.ok) throw new Error('Part details unavailable');
      const details = await response.json();
      if (controller.signal.aborted || requestGeneration.current !== generation) return;
      // Whitelist registry fields: a response cannot change a row's stable UI identity.
      setPrediction(current => numberInstances(current.map(row =>
        row.id === item.id && row.role === role && row.name === name && !row.new
          ? { ...row, identifier: details.identifier, description: details.description,
            sequence: details.sequence, sequence_length: details.sequence_length }
          : row)));
    } catch {
      if (!controller.signal.aborted && requestGeneration.current === generation) setLookupError(true);
    }
  };

  const handleNameChange = (event, newValue) => {
    patch({ name: newValue || '', identifier: '', description: '', sequence: '', sequence_length: '' });
    loadDetails(newValue);
  };

  const handleCheckedAddComponenteChange = event => {
    cancelLookup();
    patch({ new: event.target.checked, uri: event.target.checked ? '' : 'http://parts.igem.org/',
      identifier: '', name: '', description: '', sequence: '', sequence_length: '' });
  };

  const handleTexfieldChange = event => {
    cancelLookup();
    const { name, value } = event.target;
    patch({ [name]: value, ...(name === 'sequence' ? { sequence_length: value.length } : {}) });
  };

  const handleRemove = () => {
    cancelLookup();
    setPrediction(current => numberInstances(current.filter(row => row.id !== item.id)));
    setErrors(previous => {
      const next = { ...previous };
      delete next[item.id];
      return next;
    });
  };

  const ListboxComponent = forwardRef(function ListboxComponent(props, ref) {
    const { children, ...other } = props;
    const itemData = React.Children.toArray(children);
    const itemCount = itemData.length;

    const renderRow = ({ index, style }) => (
      <div style={style}>{itemData[index]}</div>
    );

    return (
      <div ref={ref} {...other}>
        <FixedSizeList
          height={300}
          width="100%"
          itemSize={36}
          itemCount={itemCount}
          itemData={itemData}
        >
          {renderRow}
        </FixedSizeList>
      </div>
    );
  });

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', boxShadow: helperText ? '1px 1px 3px 3px rgba(169, 39, 39, 1)' : '1px 1px 3px 3px #1b4a3b', borderRadius: 1.5 }}>
      <Accordion>
        <AccordionSummary
          expandIcon={<ExpandMoreIcon />}
          aria-controls={`panel${index}-content`}
          id={`panel${index}-header`}
        >
          <Typography variant='text'>
            {item.id === 'component-principal' ? "Circuit Information" : (
              <>
                {item.role || "New SubComponent"}
                {item.name && item.name !== "" && ` (${item.name})`}
                {item.instance_id && ` [${item.instance_id}]`}
              </>
            )}
          </Typography>
        </AccordionSummary>
        <AccordionDetails sx={{ pl: 2, pr: 2 }}>
          <FormControlLabel
            label="Add Custom Component (Use this option to include a component that is not available in the iGEM repository)."
            control={
              <Checkbox
                inputProps={{ 'aria-label': 'controlled' }}
                checked={checkedAddComponent}
                onChange={handleCheckedAddComponenteChange}
                sx={{
                  '& .MuiSvgIcon-root': {
                    fontSize: 18,
                    ml: .5,
                    color: 'primary.main'
                  },
                }}
              />
            }
            sx={{
              '& .MuiFormControlLabel-label': {
                textTransform: 'none',
                fontSize: '13px',
                color: 'primary.main'
              },
              mb: 1
            }}
          />

          {lookupError && <Alert severity="error" action={
            <Button onClick={() => loadDetails(item.name)}>Retry details</Button>
          }>Part details could not be loaded. Retry or choose Add Custom Component.</Alert>}
          <Box>
            <TextField
              focused
              size='small'
              placeholder="https://example.com/"
              label="URI"
              name="uri"
              value={item.uri}
              fullWidth
              margin="normal"
              onChange={handleTexfieldChange}
              disabled={!checkedAddComponent}
              error={helperText?.uri ? true : false}
              helperText={helperText?.uri}
            />

            <TextField
              focused
              size='small'
              label="Identifier"
              name="identifier"
              value={item.identifier}
              fullWidth
              margin="normal"
              placeholder='BBa_'
              onChange={handleTexfieldChange}
              disabled={!checkedAddComponent}
              error={helperText?.identifier ? true : false}
              helperText={helperText?.identifier}
            />
            <Autocomplete
              options={roles}
              name="role"
              value={item.role !== null ? item.role : ""}
              onChange={handleRoleChange}
              isOptionEqualToValue={(option, value) => option === value}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label="Role"
                  size='small'
                  margin="normal"
                  focused
                  error={helperText?.role ? true : false}
                  helperText={helperText?.role}
                />
              )}
              fullWidth
            />
            {checkedAddComponent ? (
              <>
                <TextField
                  size='small'
                  focused
                  label="Name"
                  placeholder='BBa_'
                  name="name"
                  value={item.name}
                  fullWidth
                  margin="normal"
                  onChange={handleTexfieldChange}
                  error={helperText?.name ? true : false}
                  helperText={helperText?.name}
                />
              </>
            ) : (
              <Autocomplete
                options={namesCache[item.role] || []}
                name="name"
                value={item.name || ""}
                onChange={handleNameChange}
                ListboxComponent={ListboxComponent}
                isOptionEqualToValue={(option, value) => option === value}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Name"
                    margin="normal"
                    size='small'
                    focused
                    error={helperText?.name ? true : false}
                    helperText={helperText?.name}
                  />
                )}
                fullWidth
                disabled={!item.role}
              />
            )}
            <TextField
              size='small'
              focused
              label="Description"
              name="description"
              value={item.description}
              fullWidth
              placeholder='Optional'
              margin="normal"
              onChange={handleTexfieldChange}
              disabled={!checkedAddComponent}
            />
            {item.id !== 'component-principal' && (
              <>
                <TextField
                  size='small'
                  focused
                  label="Sequence"
                  name="sequence"
                  value={item.sequence}
                  fullWidth
                  margin="normal"
                  placeholder='agactcttgctcgtactagagtgtctgc'
                  onChange={handleTexfieldChange}
                  disabled={!checkedAddComponent}
                  error={helperText?.sequence ? true : false}
                  helperText={helperText?.sequence}
                />
                <TextField
                  size='small'
                  focused
                  label="Sequence Length"
                  name="sequence_length"
                  value={item.sequence_length}
                  fullWidth
                  margin="normal"
                  onChange={handleTexfieldChange}
                  disabled
                  error={helperText?.sequence_length ? true : false}
                  helperText={helperText?.sequence_length}
                />
              </>
            )}
          </Box>
          <Divider sx={{ mt: 2 }} />
        </AccordionDetails>

        {item.id !== 'component-principal' && (
          <Box sx={{ display: 'flex', justifyContent: 'right' }}>
            <IconButton
              onClick={handleRemove}
              sx={{ mb: 2, mr: 2 }}
              color='primary'
            >
              <DeleteIcon />
            </IconButton>

          </Box>

        )}

      </Accordion>
    </Box>
  );
};

export default PredictionAccordion;
