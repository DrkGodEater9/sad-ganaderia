import { Component } from "react";

// Red de seguridad: si algo revienta al renderizar (un dato inesperado del
// backend, etc.), muestra un mensaje normal en vez de dejar la pantalla en
// blanco. Tiene que ser un componente de clase: React solo soporta
// getDerivedStateFromError/componentDidCatch en clases, no en hooks.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Error inesperado en la app:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="contenido">
          <p className="texto-estado texto-estado-error">
            Ocurrió un error inesperado. Intenta recargar la página; si sigue pasando, avísale a quien
            mantiene la app.
          </p>
          <button
            type="button"
            className="boton boton-secundario boton-ancho"
            onClick={() => this.setState({ error: null })}
          >
            Reintentar
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
