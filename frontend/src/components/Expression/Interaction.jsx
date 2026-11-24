/* eslint-disable react/prop-types */
import { useState, useEffect } from 'react';
import { Box, Autocomplete, TextField, IconButton, Typography, Divider, Alert, Button } from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import AddCircleOutlineIcon from '@mui/icons-material/AddCircleOutline';
import { participantOptions, sameParticipantSource, selectParticipant } from '../../utils/FunctionalPayload.js';

const interactionTypeOptions = ['Inhibition', 'Stimulation', 'Biochemical Reaction', 'Non-Covalent Binding', 'Degradation', 'Control', 'Genetic Production'];

const Interaction = ({ interactions, setInteractions, interactionIndex, interaction = {}, eds, prediction, helperText, setErrors, participantRoles, setParticipantRoles, API_BASE_URL }) => {
  const [lookupFailed, setLookupFailed] = useState(false);
  const [lookupAttempt, setLookupAttempt] = useState(0);
  const [componentOptions, setComponentOptions] = useState([]);

  useEffect(() => {
    setComponentOptions(participantOptions(prediction, eds));
  }, [eds, prediction]);

  useEffect(() => {
    if (!interaction?.type) return;
    const controller = new AbortController();
    setLookupFailed(false);
    const fetchParticipantRoles = async () => {
      try {
        const response = await fetch(
          `${API_BASE_URL}/component/interactions?interaction_type=${encodeURIComponent(interaction.type)}`,
          { signal: controller.signal },
        );
        if (!response.ok) throw new Error('Cannot fetch participation roles');
        const roles = await response.json();
        if (!Array.isArray(roles)) throw new Error('Invalid participation roles');
        if (controller.signal.aborted) return;
        setParticipantRoles(previous => ({ ...previous, [interaction.id]: roles }));
        setInteractions(previous => previous.map(item => item.id === interaction.id && item.type === interaction.type ? {
          ...item,
          participants: Object.fromEntries(roles.map(role => [role,
            item.participants?.[role] || [{ id: crypto.randomUUID(), name: '', instance_id: '' }],
          ])),
        } : item));
      } catch {
        if (!controller.signal.aborted) {
          setLookupFailed(true);
        }
      }
    };
    fetchParticipantRoles();
    return () => controller.abort();
  }, [API_BASE_URL, interaction.id, interaction.type, setInteractions, setParticipantRoles, lookupAttempt]);

  const handleInteractionChange = (interactionIndex, field, value) => {
    const updatedInteractions = [...interactions];
    updatedInteractions[interactionIndex] = {
      ...updatedInteractions[interactionIndex],
      [field]: value,
    };
    setInteractions(updatedInteractions);
  };

  const handleParticipantChange = (interactionIndex, role, participantIndex, selectedOption) => {
    setInteractions(previous => previous.map((item, index) => index === interactionIndex ? {
      ...item,
      participants: {
        ...item.participants,
        [role]: (item.participants[role] || []).map((row, rowIndex) => rowIndex === participantIndex
          ? selectParticipant(row, selectedOption) : row),
      },
    } : item));
  };

  const handleAddParticipant = (interactionIndex, role) => {
    const newParticipant = { id: crypto.randomUUID(), name: '', instance_id: '' };
    setInteractions(previous => previous.map(row => row.id === interaction.id ? {
      ...row, participants: { ...row.participants,
        [role]: [...(row.participants[role] || []), newParticipant] },
    } : row));
  };

  const handleRemoveInteraction = (interactionIndex) => {

    const updatedInteractions = [...interactions];
    updatedInteractions.splice(interactionIndex, 1);
    setInteractions(updatedInteractions);

    setErrors((prevErrors) => {
      const updatedErrors = { ...prevErrors };
      if (interactions[interactionIndex]?.id) {
        delete updatedErrors[interactions[interactionIndex].id];
      }
      return updatedErrors;
    })

    setParticipantRoles((prevRoles) => {
      const updatedRoles = { ...prevRoles };
      if (interactions[interactionIndex].id) {
        delete updatedRoles[interactions[interactionIndex].id];
      }
      return updatedRoles;
    });

  };

  const handleRemoveParticipant = (interactionIndex, role, participantId) => {
    setInteractions(previous => previous.map(row => row.id === interaction.id ? {
      ...row, participants: { ...row.participants,
        [role]: (row.participants[role] || []).filter(participant => participant.id !== participantId) },
    } : row));
    setErrors(previous => {
      const next = structuredClone(previous);
      if (next[interaction.id]?.participants?.[role]) delete next[interaction.id].participants[role][participantId];
      return next;
    });
  };

  return (
    <Box>
      {lookupFailed && <Alert severity="error" action={
        <Button onClick={() => setLookupAttempt(value => value + 1)}>Retry interaction roles</Button>
      }>Participation roles could not be loaded. Your edits have been kept.</Alert>}
      <Box
        key={interactionIndex}
      >
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          <Autocomplete
            options={interactionTypeOptions}
            value={interaction?.type || null}
            onChange={(event, newValue) =>
              handleInteractionChange(interactionIndex, 'type', newValue)
            }
            renderInput={(params) => (
              <TextField
                {...params}
                label="Interaction Type"
                size="small"
                error={helperText?.type ? true : false}
                helperText={helperText?.type}
                focused
              />
            )}
            sx={{ pt: 2 }}
          />
          {Array.isArray(participantRoles) && participantRoles.map((role, idx) => (
            <Box key={idx} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Box sx={{ display: 'flex', flexDirection: 'row', alignItems: 'center' }}>
                <Typography>{role}</Typography>
                <IconButton
                  onClick={() => handleAddParticipant(interactionIndex, role)}
                  color="primary"
                  size="small"
                >
                  <AddCircleOutlineIcon />
                </IconButton>
              </Box>
              {(interaction?.participants?.[role] || []).map((participant, pIdx) => (

                <Box key={pIdx} sx={{ display: 'flex', flexDirection: 'row', alignItems: 'center' }}>
                  <Autocomplete
                    options={componentOptions}
                    value={componentOptions.find(option => sameParticipantSource(option, participant)) || null}
                    getOptionLabel={(option) => option.label}
                    isOptionEqualToValue={sameParticipantSource}
                    onChange={(event, newValue) =>
                      handleParticipantChange(interactionIndex, role, pIdx, newValue)
                    }
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        label={role}
                        size="small"
                        error={helperText?.participants?.[role]?.[participant.id]?.name ? true : false}
                        helperText={helperText?.participants?.[role]?.[participant.id]?.name}

                        focused
                      />
                    )}
                    fullWidth
                  />
                  {pIdx > 0 && (
                    <IconButton
                      onClick={() => handleRemoveParticipant(interactionIndex, role, participant.id)}
                      color="primary"
                      size="small"
                      sx={{ ml: 1 }}
                    >
                      <DeleteIcon />
                    </IconButton>
                  )}
                </Box>
              ))}

            </Box>
          ))}

          <Divider />
          <Box sx={{ display: 'flex', justifyContent: 'right' }}>
            <IconButton
              onClick={() => handleRemoveInteraction(interactionIndex)}
              color="primary"
            >
              <DeleteIcon />
            </IconButton>
          </Box>
        </Box>
      </Box>
    </Box>
  );
};

export default Interaction;
