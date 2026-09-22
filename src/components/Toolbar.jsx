export default function Toolbar({ onUndo, onCancel, onClose, canClose, disabled }) {
  return (
    <div className="toolbar">
      <button onClick={onUndo} disabled={disabled}>
        Deshacer último punto
      </button>
      <button onClick={onCancel} disabled={disabled}>
        Cancelar potrero actual
      </button>
      <button className="primary" onClick={onClose} disabled={disabled || !canClose}>
        Cerrar potrero
      </button>
    </div>
  );
}
