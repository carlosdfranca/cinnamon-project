# usuarios/middleware.py
from django.utils.deprecation import MiddlewareMixin
from usuarios.models import Empresa

class EmpresaAtivaMiddleware(MiddlewareMixin):
    """
    Carrega a empresa ativa a partir da sessão e injeta em request.empresa_ativa.
    """
    SESSION_KEY = "empresa_ativa_id"

    def process_request(self, request):
        request.empresa_ativa = None
        emp_id = request.session.get(self.SESSION_KEY)
        if emp_id:
            try:
                request.empresa_ativa = Empresa.objects.only("id", "nome").get(id=emp_id)
            except Empresa.DoesNotExist:
                # Limpa sessão se ID inválido
                request.session.pop(self.SESSION_KEY, None)
