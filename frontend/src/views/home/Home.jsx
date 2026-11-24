/* eslint-disable no-unused-vars */
import { useState, useContext, useRef, useEffect, useCallback } from 'react';
import { Container, Paper, Box, Button, Typography, Dialog, DialogTitle, DialogContent, DialogActions } from '@mui/material';
import NoteAddIcon from '@mui/icons-material/NoteAdd';
import NameContext from '../../context/NameContext';
import CameraCapture from '../../components/CameraCapture/CameraCapture';
import FileUpload from '../../components/FileUpload/FileUpload';
import ImageDisplay from '../../components/ImageDisplay/ImageDisplay';
import NamespaceInput from '../../components/NamespaceInput/NamespaceInput';
import PredictionSection from '../../components/PredictionSection/PredictionSection';
import FunctionalSystem from '../../components/FunctionalSystem/FunctionalSystem';
import { updatePredictions } from '../../utils/PredictionUtils';
import { getImageForRole } from '../../utils/ImageUtils.jsx';
import ConfirmationDialog from '../../components/ConfirmationDialog/ConfirmationDialog';
import ConversionDialog from '../../components/ConversionDialog/ConversionDialog';
import { validateForm } from '../../utils/ValidationUtils.jsx';
import { conversionArtifacts } from '../../utils/Conversion.js';
import { functionalPayload, responseError, ParticipantSelectionError } from '../../utils/FunctionalPayload.js';
import ErrorAlertDialog from '../../components/ErrorAlertDialog/ErrorAlertDialog.jsx';
import Welcome from '../../components/Welcome/Welcome.jsx';
import LoadingScreen from '../../components/LoadingScreen/LoadingScreen.jsx';
import GenericModal from '../../components/GenericModal/GenericModal.jsx';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api';

export default function Home() {
  const [resetOpen, setResetOpen] = useState(false);
  const [designEpoch, setDesignEpoch] = useState(0);
  const resetDesign = () => {
    stream?.getTracks().forEach(track => track.stop());
    setStream(null);
    setPrediction(null);
    setNamespace('');
    setExpressions([]);
    setInteractions([]);
    setEds([]);
    setErrors({});
    setParticipantRoles({});
    setImageElement(null);
    setHasPredictions(false);
    setStructuralHandle(null);
    setPredictionName(null);
    setOpenConversionDialog(false);
    setDesignEpoch(value => value + 1);
    setResetOpen(false);
  };
  const [prediction, setPrediction] = useState(null);
  const [namespace, setNamespace] = useState("");
  const [expressions, setExpressions] = useState([]);
  const [interactions, setInteractions] = useState([]);
  const [eds, setEds] = useState([]);

  const [errors, setErrors] = useState({});

  const [imageElement, setImageElement] = useState(null);

  const { namesCache } = useContext(NameContext);
  const [stream, setStream] = useState(null);
  const [loading, setLoading] = useState(null);
  const [isScrollable, setIsScrollable] = useState(false);
  const containerRef = useRef(null);
  const [openDialog, setOpenDialog] = useState(false);
  const [openConversionDialog, setOpenConversionDialog] = useState(false);
  const [structuralHandle, setStructuralHandle] = useState(null);
  const [openDialogAlert, setOpenDialogAlert] = useState(false);
  const isButtonVisible = true;

  const [participantRoles, setParticipantRoles] = useState({});
  const [hasPredictions, setHasPredictions] = useState(false);

  const [predictionName, setPredictionName] = useState(null);

  const [modalConfig, setModalConfig] = useState({ open: false, title: "", message: "", type: "info" });

  useEffect(() => {
    const checkScroll = () => {
      if (containerRef.current) {
        const { scrollWidth, clientWidth } = containerRef.current;
        setIsScrollable(scrollWidth > clientWidth);
      }
    };
    checkScroll();
    window.addEventListener("resize", checkScroll);
    return () => window.removeEventListener("resize", checkScroll);
  }, []);

  useEffect(() => {
    return () => {
      if (stream) {
        stream.getTracks().forEach(track => track.stop());
      }
    };
  }, [stream]);

  const showModal = useCallback((title, message, type) => {
    setModalConfig({ open: true, title, message, type });
  }, []);

  const closeModal = () => {
    setModalConfig({ ...modalConfig, open: false });
  };

  const handleDialogAlertClose = () => {
    setOpenDialogAlert(false);
  };

  const handleOpenDialog = () => {
    setOpenDialog(true);
  };

  const handleCloseDialog = () => {
    setOpenDialog(false);
  };

  const handleConfirmSubmit = () => {
    handleCloseDialog();
    handleSubmit();
  };

  const handleSubmit = async () => {

    const validationErrors = validateForm({ namespace, prediction, expressions, interactions, eds }, participantRoles);

    if (validationErrors) {
      setErrors(validationErrors);
      setOpenDialogAlert(true);

      setTimeout(() => {
        setOpenDialogAlert(false);
      }, 3000);

      return;
    } else {
      setErrors({});
    }

    const processedComponents = prediction.map(({ availableNames, ...rest }) => rest);

    try {
      const dataToSend = {
        namespace: namespace.replace(/\/+$/, ""),
        components: processedComponents,
        ...functionalPayload(expressions, interactions, eds, processedComponents),
      };
      setLoading("sbolGeneration");
      const response = await fetch(`${API_BASE_URL}/file/create`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(dataToSend),
      });

      if (response.ok) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', `${prediction[0].name}.xml`);
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);

        const createdHandle = response.headers.get('X-GCAI-Structural-Handle');
        if (!/^v1_[A-Za-z0-9_-]{43}$/.test(createdHandle || '')) throw new Error('Missing conversion handle');
        setOpenConversionDialog(true);
        setStructuralHandle(createdHandle);
        setPredictionName(prediction[0].name);
        setLoading(null);
      } else {
        showModal("Error", await responseError(response), "error");
      }
    } catch (error) {
      setLoading(null);
      showModal("Error", error instanceof ParticipantSelectionError
        ? error.message : "The request could not be completed. Your design has been kept; please retry.", "error");
    } finally {
      setLoading(null);
    }
  };

  const handleConvert = async (formats, handle) => {
    setLoading('conversion');
    try {
      const response = await fetch(`${API_BASE_URL}/file/convert`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ structural_handle: handle, ...formats }),
      });
      if (!response.ok) throw new Error(await responseError(response));
      const downloads = await conversionArtifacts(await response.blob(), formats);
      for (const file of downloads) {
        const url = window.URL.createObjectURL(new Blob([file.data]));
        const link = document.createElement('a');
        link.href = url;
        link.download = `${predictionName}${file.name.endsWith('.fasta') ? '.fasta' : '.gb'}`;
        link.click();
        window.URL.revokeObjectURL(url);
      }
      setOpenConversionDialog(false);
      showModal('Success', 'Files converted successfully!', 'success');
    } catch (error) {
      setOpenConversionDialog(true);
      showModal('Error', error.message || 'Conversion failed. Your handle and design have been kept; please retry.', 'error');
    } finally {
      setLoading(null);
    }
  };

  return (
    <>
      {(<Container maxWidth="md" sx={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
        <Paper elevation={3} sx={{ p: 5, mt: 2, width: '100%', border: '3px solid #1b4a3b', borderRadius: 2, boxShadow: '1px 1px 15px 5px #1b4a3b', mb: 2, height: '100%' }}>
          <Box sx={{ display: 'flex', flexDirection: 'column' }}>
            {loading && <LoadingScreen message={loading} />}
            <Button disabled={Boolean(loading)} onClick={() => setResetOpen(true)}>New design</Button>
            <Box component="fieldset" disabled={Boolean(loading)} sx={{ border: 0, p: 0, m: 0 }}>

            {!loading && !prediction && !stream && <Welcome />}
            {(
              <>
                <CameraCapture key={designEpoch}
                  setLoading={setLoading}
                  setImageElement={setImageElement}
                  stream={stream}
                  setStream={setStream}
                  setHasPredictions={setHasPredictions}
                  prediction={prediction}
                  setPrediction={setPrediction}
                  setNamespace={setNamespace}
                  setExpressions={setExpressions}
                  setEds={setEds}
                  setErrors={setErrors}
                  setInteractions={setInteractions}
                  updatePredictions={updatePredictions}
                  showModal={showModal}
                  API_BASE_URL={API_BASE_URL}
                />
                <FileUpload
                  setLoading={setLoading}
                  setHasPredictions={setHasPredictions}
                  setImageElement={setImageElement}
                  prediction={prediction}
                  setPrediction={setPrediction}
                  stream={stream}
                  setNamespace={setNamespace}
                  setExpressions={setExpressions}
                  setEds={setEds}
                  setErrors={setErrors}
                  setInteractions={setInteractions}
                  updatePredictions={updatePredictions}
                  showModal={showModal}
                  API_BASE_URL={API_BASE_URL}
                />
              </>
            )}

            {prediction && imageElement && (
              <>
                <ImageDisplay
                  imageElement={imageElement}
                  prediction={prediction}
                  getImageForRole={getImageForRole}
                  containerRef={containerRef}
                  isScrollable={isScrollable}
                  hasPredictions={hasPredictions}
                />

                <NamespaceInput
                  namespace={namespace}
                  setNamespace={setNamespace}
                  error={Boolean(errors.namespace)}
                  helperText={errors.namespace}
                />

                <PredictionSection
                  prediction={prediction}
                  setPrediction={setPrediction}
                  error={Boolean(errors.prediction)}
                  helperText={errors.prediction}
                  setErrors={setErrors}
                  showModal={showModal}
                  API_BASE_URL={API_BASE_URL}
                />
                <FunctionalSystem
                  expressions={expressions}
                  setExpressions={setExpressions}
                  interactions={interactions}
                  setInteractions={setInteractions}
                  eds={eds}
                  setEds={setEds}
                  participantRoles={participantRoles}
                  setParticipantRoles={setParticipantRoles}
                  prediction={prediction}
                  error={Boolean(errors)}
                  helperText={errors}
                  setErrors={setErrors}
                  showModal={showModal}
                  API_BASE_URL={API_BASE_URL}
                />
                <Box>
                  {isButtonVisible && (
                    <Button variant="contained" color="primary" onClick={handleOpenDialog} startIcon={<NoteAddIcon />} sx={{ mt: 2.5, p: 1 }} fullWidth>
                      Create SBOL 3 File
                    </Button>
                  )}
                </Box>
              </>
            )}
            </Box>
          </Box>

        </Paper>

        <Dialog open={resetOpen} onClose={() => setResetOpen(false)}>
          <DialogTitle>Discard this design?</DialogTitle>
          <DialogContent>New design clears all edits and conversion settings.</DialogContent>
          <DialogActions>
            <Button onClick={() => setResetOpen(false)}>Keep editing</Button>
            <Button onClick={resetDesign}>Discard and start new</Button>
          </DialogActions>
        </Dialog>
        <ConfirmationDialog
          open={openDialog}
          handleClose={handleCloseDialog}
          handleConfirm={handleConfirmSubmit}
        />

        <ConversionDialog
          key={designEpoch}
          open={openConversionDialog}
          handleClose={() => setOpenConversionDialog(false)} handleConvert={(format) => handleConvert(format, structuralHandle)}
        />

        <ErrorAlertDialog
          open={openDialogAlert}
          onClose={handleDialogAlertClose}
        />

        <GenericModal
          open={modalConfig.open}
          onClose={closeModal}
          title={modalConfig.title}
          message={modalConfig.message}
          type={modalConfig.type}
        />

      </Container>)}
    </>

  );

}
