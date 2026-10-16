import io
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection, connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from openpyxl import Workbook
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.test import APIClient

from audit.models import AuditEvent
from organizations.models import Membership
from organizations.services import create_organization
from products import services as catalog
from products import workflows
from products.models import AttributeClaim, ClaimSelection, Evidence, Product

from . import parsers, services
from .models import Candidate, ImportJob, ReviewRecord
from .serializers import DecisionInput, MappingInput


def file(data=b"sku,name,mass,mass_unit\nA,Carton,1200,g\n", name="source.csv", mime="text/csv"):
    return SimpleUploadedFile(name, data, content_type=mime)


def workbook(rows, extra_sheet=False):
    book = Workbook()
    for row in rows:
        book.active.append(row)
    if extra_sheet:
        book.create_sheet("Selected").append(["sku", "name"])
        book["Selected"].append(["SHEET", "Selected product"])
    out = io.BytesIO()
    book.save(out)
    return file(
        out.getvalue(),
        "source.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def pdf(text="SKU: PDF-1\nName: Supplier carton\nWeight: 1.35 kg", encrypted=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=400, height=600)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    stream.set_data(
        (
            "BT /F1 12 Tf 20 550 Td "
            + " ".join(f"({line}) Tj 0 -16 Td" for line in text.splitlines())
            + " ET"
        ).encode()
    )
    page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("test-secret")
    out = io.BytesIO()
    writer.write(out)
    return file(out.getvalue(), "source.pdf", "application/pdf")


class ImportFixture:
    def setup_fixture(self):
        cache.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.storage_override = override_settings(
            STORAGES={
                **settings.STORAGES,
                "ingestion": {
                    "BACKEND": "ingestion.storage.PrivateStorage",
                    "OPTIONS": {"location": self.tmp.name},
                },
            }
        )
        self.storage_override.enable()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.storage_override.disable)
        self.owner = get_user_model().objects.create_user(
            "import-owner", password="Local-only-strong!2026"
        )
        self.member = get_user_model().objects.create_user("import-member")
        self.other = get_user_model().objects.create_user("import-other")
        self.org = create_organization(self.owner, name="Import lab", slug="import-lab")
        self.foreign = create_organization(self.other, name="Other lab", slug="other-lab")
        Membership.objects.create(user=self.member, organization=self.org, role="member")
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.base = f"/api/v1/organizations/{self.org.pk}/imports/"

    def prepared(self, source=None, mapping=None):
        job = services.upload(self.owner, self.org.pk, source or file())
        job = services.validate(
            self.owner,
            self.org.pk,
            job.pk,
            {
                "expected_version": job.version,
                "header_row": 1,
                "sheet": "",
                "delimiter": "," if job.format == "csv" else "",
            },
        )
        self.assertEqual(job.status, "uploaded", job.errors)
        mapping = mapping or {
            h: h
            for h in job.preview["headers"]
            if h
            in {
                "sku",
                "name",
                "mass",
                "mass_unit",
                "package_name",
                "package_type",
                "quantity",
                "length",
                "dimension_unit",
                "manufacturer",
            }
        }
        job = services.map_fields(
            self.owner, self.org.pk, job.pk, {"expected_version": job.version, "mapping": mapping}
        )
        return services.process(self.owner, self.org.pk, job.pk, {"expected_version": job.version})

    def approve(self, job, *, select=False):
        for row in job.rows.all():
            if not row.product_id:
                services.approve_creation(
                    self.owner,
                    self.org.pk,
                    job.pk,
                    row.pk,
                    {"allow_create": True, "reason": "Reviewed new product"},
                )
        for candidate in Candidate.objects.filter(row__job=job):
            values = catalog.validated(
                DecisionInput,
                {
                    "expected_version": candidate.version,
                    "decision": "approve",
                    "reason": "Compared source with catalog",
                    "select_value": select and candidate.field == "mass",
                },
            )
            services.review(self.owner, self.org.pk, job.pk, candidate.pk, values)
        job.refresh_from_db()
        return job


class IngestionTests(ImportFixture, TestCase):
    def setUp(self):
        self.setup_fixture()

    def test_upload_is_private_and_metadata_is_not_mass_assignable(self):
        response = self.client.post(
            self.base, {"file": file(b"sku,name\nA,Box\n", "../../unsafe.csv")}, format="multipart"
        )
        self.assertEqual(response.status_code, 201, response.content)
        result = response.json()
        job = ImportJob.objects.get(pk=result["id"])
        self.assertNotIn("..", job.storage_key)
        self.assertTrue(job.storage_key.startswith(str(self.org.pk)))
        self.assertNotIn("storage_key", result)
        self.assertNotIn(self.tmp.name, str(result))
        self.assertEqual(
            self.client.patch(self.base + f"{job.pk}/", {"status": "completed"}).status_code, 405
        )
        self.assertEqual(
            self.client.post(
                self.base,
                {"file": file(), "organization": str(self.foreign.pk)},
                format="multipart",
            ).status_code,
            400,
        )

    def test_anonymous_upload_and_session_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        self.assertEqual(
            client.post(self.base, {"file": file()}, format="multipart").status_code, 403
        )
        client.force_login(self.owner)
        self.assertEqual(
            client.post(self.base, {"file": file()}, format="multipart").status_code, 403
        )
        token = client.get("/api/v1/auth/csrf/").json()["csrfToken"]
        self.assertEqual(
            client.post(
                self.base, {"file": file()}, format="multipart", HTTP_X_CSRFTOKEN=token
            ).status_code,
            201,
        )

    def test_types_size_encoding_and_scanner_gate(self):
        with override_settings(INGESTION_LIMITS={**settings.INGESTION_LIMITS, "upload_bytes": 4}):
            response = self.client.post(self.base, {"file": file()}, format="multipart")
            self.assertEqual(response.status_code, 400)
            self.assertIn("byte limit", str(response.data))
        for source in [
            file(name="x.exe"),
            file(name="x.csv", mime="application/pdf"),
            file(b"PK\x03\x04", name="x.csv"),
            file(b"bad\x00text"),
        ]:
            with self.subTest(source=source.name), self.assertRaises(ValidationError):
                services.upload(self.owner, self.org.pk, source)
        with (
            override_settings(INGESTION_LIMITS={**settings.INGESTION_LIMITS, "upload_bytes": 4}),
            self.assertRaises(ValidationError),
        ):
            services.upload(self.owner, self.org.pk, file())
        with (
            override_settings(INGESTION_ALLOW_UNSCANNED=False),
            self.assertRaises(PermissionDenied),
        ):
            services.upload(self.owner, self.org.pk, file())

    def test_csv_bom_quotes_delimiters_empty_rows_and_mappings(self):
        source = file(
            '\ufeffCode;Product;Mass;Unit\r\nA;"Carton; large";1.2;kg\r\n;;;\r\n'.encode()
        )
        job = services.upload(self.owner, self.org.pk, source)
        job = services.validate(
            self.owner,
            self.org.pk,
            job.pk,
            {"expected_version": 1, "header_row": 1, "sheet": "", "delimiter": ""},
        )
        self.assertEqual(job.preview["row_count"], 1)
        self.assertEqual(job.preview["sample"][0]["cells"]["Product"], "Carton; large")
        job = services.map_fields(
            self.owner,
            self.org.pk,
            job.pk,
            {
                "expected_version": job.version,
                "mapping": {"sku": "Code", "name": "Product", "mass": "Mass", "mass_unit": "Unit"},
            },
        )
        job = services.process(self.owner, self.org.pk, job.pk, {"expected_version": job.version})
        self.assertEqual(job.status, "awaiting_review")
        self.assertFalse(Product.objects.exists())
        utf16 = services.upload(self.owner, self.org.pk, file("sku,name\nB,Box\n".encode("utf-16")))
        self.assertEqual(parsers.parse(utf16, {"delimiter": ","})["rows"][0]["cells"]["sku"], "B")

    def test_bad_headers_row_width_and_limits_fail_safely(self):
        for data in [b"sku,SKU\nA,B\n", b"sku,\nA,B\n", b"", b'sku,name\n"unterminated']:
            if not data:
                continue
            job = services.upload(self.owner, self.org.pk, file(data))
            with self.assertRaises(ValidationError):
                parsers.parse(job, {"delimiter": ","})
        job = services.upload(self.owner, self.org.pk, file(b"sku,name\nA,Box,Extra\nB,Safe\n"))
        parsed = parsers.parse(job, {"delimiter": ","})
        self.assertTrue(parsed["rows"][0]["errors"])
        self.assertFalse(parsed["rows"][1]["errors"])
        with (
            override_settings(INGESTION_LIMITS={**settings.INGESTION_LIMITS, "rows": 1}),
            self.assertRaises(ValidationError),
        ):
            parsers.parse(job, {"delimiter": ","})

    def test_xlsx_sheet_selection_formula_and_archive_limits(self):
        job = services.upload(
            self.owner,
            self.org.pk,
            workbook(
                [["preamble"], ["sku", "name", "mass", "mass_unit"], ["A", "Box", "=1+1", "kg"]],
                extra_sheet=True,
            ),
        )
        parsed = parsers.parse(job, {"header_row": 2})
        self.assertEqual(parsed["rows"][0]["cells"]["mass"], "[UNSUPPORTED FORMULA]")
        selected = parsers.parse(job, {"sheet": "Selected", "header_row": 1})
        self.assertEqual(selected["rows"][0]["cells"]["sku"], "SHEET")
        with (
            override_settings(INGESTION_LIMITS={**settings.INGESTION_LIMITS, "sheets": 1}),
            self.assertRaises(ValidationError),
        ):
            parsers.parse(job, {"header_row": 2})
        with (
            override_settings(
                INGESTION_LIMITS={**settings.INGESTION_LIMITS, "unpacked_bytes": 100}
            ),
            self.assertRaises(ValidationError),
        ):
            parsers.parse(job, {"header_row": 2})

    def test_malformed_zip_xml_external_links_and_path_entries_fail_safely(self):
        for name, data in [("bad.xlsx", b"PK\x03\x04bad"), ("bad.pdf", b"%PDF-invalid")]:
            mime = (
                "application/pdf"
                if name.endswith("pdf")
                else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            job = services.upload(self.owner, self.org.pk, file(data, name, mime))
            result = services.validate(self.owner, self.org.pk, job.pk, {"expected_version": 1})
            self.assertEqual(result.status, "failed")
            self.assertNotIn(self.tmp.name, str(result.errors))
        for entry in ["../escape.xml", "xl/vbaProject.bin", "xl/externalLinks/externalLink1.xml"]:
            source = workbook([["sku", "name"], ["A", "Box"]])
            buf = io.BytesIO(source.read())
            with zipfile.ZipFile(buf, "a") as archive:
                archive.writestr(entry, "untrusted")
            job = services.upload(
                self.owner, self.org.pk, file(buf.getvalue(), "bad.xlsx", source.content_type)
            )
            with self.assertRaises(ValidationError):
                parsers.parse(job, {})

    def test_pdf_and_text_preserve_page_location_without_inventing_units(self):
        job = self.prepared(pdf())
        mass = Candidate.objects.get(row__job=job, field="mass")
        self.assertEqual(mass.normalized["canonical_unit"], "kg")
        self.assertEqual(mass.row.location, "page 1")
        self.assertEqual(mass.raw_value, "1.35")
        # Source bytes, page location, magnitude and declared unit persist.
        self.assertEqual(mass.proposed["unit"], "kg")
        bad = services.upload(self.owner, self.org.pk, pdf(encrypted=True))
        with self.assertRaises(ValidationError):
            parsers.parse(bad, {})
        textjob = self.prepared(
            file(b"SKU: TXT-1\nName: Supplier box\nWeight: 12\n", "sheet.txt", "text/plain")
        )
        self.assertEqual(Candidate.objects.get(row__job=textjob, field="mass").quality, "invalid")

    def test_candidates_do_not_create_catalog_until_approved_and_apply_is_idempotent(self):
        job = self.prepared()
        self.assertFalse(Product.objects.exists())
        with self.assertRaises(ValidationError):
            services.apply(self.owner, self.org.pk, job.pk, {"expected_version": job.version})
        job = self.approve(job, select=True)
        applied = services.apply(self.owner, self.org.pk, job.pk, {"expected_version": job.version})
        self.assertEqual(applied.status, "completed")
        self.assertEqual(Product.objects.count(), 1)
        claim = AttributeClaim.objects.get()
        self.assertEqual(claim.basis, "reported")
        self.assertEqual(claim.canonical_value, Decimal("1.2"))
        self.assertEqual(ClaimSelection.objects.count(), 1)
        self.assertEqual(Evidence.objects.count(), 1)
        before = AuditEvent.objects.count()
        services.apply(self.owner, self.org.pk, job.pk, {"expected_version": job.version})
        self.assertEqual(Evidence.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.count(), before)
        self.assertTrue(job.rows.get().evidence.source_reference.startswith(f"import:{job.pk}"))

    def test_rejected_invalid_candidates_and_corrections_remain_traceable(self):
        job = self.prepared(file(b"sku,name,mass,mass_unit\nA,Box,12,lb\n"))
        mass = Candidate.objects.get(row__job=job, field="mass")
        self.assertEqual(mass.quality, "invalid")
        result = services.review(
            self.owner,
            self.org.pk,
            job.pk,
            mass.pk,
            catalog.validated(
                DecisionInput,
                {
                    "expected_version": 1,
                    "decision": "approve",
                    "value": "1.2",
                    "unit": "kg",
                    "reason": "Corrected declared units from source",
                },
            ),
        )
        self.assertEqual(result.raw_value, "12")
        self.assertEqual(result.normalized["unit"], "kg")
        values = catalog.validated(
            DecisionInput,
            {
                "expected_version": result.version,
                "decision": "reject",
                "reason": "Uncertain supplier value",
            },
        )
        result = services.review(self.owner, self.org.pk, job.pk, mass.pk, values.copy())
        before = ReviewRecord.objects.count()
        services.review(self.owner, self.org.pk, job.pk, mass.pk, values.copy())
        self.assertEqual(ReviewRecord.objects.count(), before)
        self.assertEqual(result.decision, "reject")
        history = job.reviews.filter(candidate=mass)
        self.assertEqual(history.count(), 2)
        with self.assertRaises(ValueError):
            history.first().delete()

    def test_equivalent_units_competing_candidates_and_empty_cells(self):
        product = catalog.create_product(
            self.owner,
            self.org.pk,
            {
                "sku": "A",
                "revision": {
                    "name": "Existing box",
                    "manufacturer": "Retain manufacturer",
                    "change_reason": "Initial",
                },
            },
        )
        source = catalog.create_evidence(
            self.owner,
            self.org.pk,
            product.pk,
            {
                "title": "Reference",
                "source_type": "manual",
                "source_reference": "local fixture",
                "attribution": "Tester",
                "license": "Internal",
                "observed_at": timezone.now(),
            },
        )
        workflows.create_claim(
            self.owner,
            self.org.pk,
            product.pk,
            {
                "attribute": "mass",
                "basis": "reported",
                "value": "1.2",
                "unit": "kg",
                "observed_at": source.observed_at,
                "evidence_id": str(source.pk),
            },
        )
        job = self.prepared(
            file(b"sku,name,manufacturer,mass,mass_unit\nA,,,1200,g\nA,,,1.2,kg\nA,,,1.35,kg\n")
        )
        claims = list(Candidate.objects.filter(row__job=job, field="mass"))
        self.assertTrue(all(c.quality == "conflict" for c in claims))
        self.assertFalse(Candidate.objects.filter(row__job=job, field="manufacturer").exists())
        self.assertTrue(claims[0].proposed["competing"])
        package_job = self.prepared(
            file(b"sku,package_name,package_type,mass,mass_unit\nA,New case,case,1.35,kg\n")
        )
        self.assertEqual(Candidate.objects.get(row__job=package_job, field="mass").quality, "new")
        # Without the contradictory row, normalized equivalent units do not conflict.
        other = self.prepared(file(b"sku,mass,mass_unit\nA,1200,g\nA,1.2,kg\n"))
        self.assertTrue(
            all(c.quality == "equivalent" for c in Candidate.objects.filter(row__job=other))
        )

    def test_existing_changes_require_refresh_and_a_failed_apply_rolls_back(self):
        job = self.approve(self.prepared())
        with (
            patch("ingestion.services.event", side_effect=RuntimeError("audit unavailable")),
            self.assertRaises(RuntimeError),
        ):
            services.apply(self.owner, self.org.pk, job.pk, {"expected_version": job.version})
        self.assertFalse(Product.objects.exists())
        self.assertFalse(Evidence.objects.exists())
        job.refresh_from_db()
        self.assertEqual(job.status, "awaiting_review")
        catalog.create_product(
            self.owner,
            self.org.pk,
            {"sku": "A", "revision": {"name": "Concurrent", "change_reason": "Initial"}},
        )
        with self.assertRaises(catalog.Conflict):
            services.apply(self.owner, self.org.pk, job.pk, {"expected_version": job.version})
        services.refresh(self.owner, self.org.pk, job.pk, {"expected_version": job.version})
        self.assertTrue(Candidate.objects.filter(row__job=job, decision="pending").exists())

    def test_packaging_import_preserves_scope_and_archival_denies_writes(self):
        job = self.approve(
            self.prepared(
                file(
                    b"sku,name,package_name,package_type,quantity,length,dimension_unit\n"
                    b"A,Box,Shipping case,case,6,12,cm\n"
                )
            )
        )
        services.apply(self.owner, self.org.pk, job.pk, {"expected_version": job.version})
        product = Product.objects.get()
        packaging = product.configurations.get()
        self.assertEqual(packaging.quantity, 6)
        self.assertEqual(AttributeClaim.objects.get().packaging, packaging)
        job = self.approve(
            self.prepared(file(b"sku,package_name,length,dimension_unit\nA,Shipping case,15,cm\n"))
        )
        workflows.configuration_state(
            self.owner,
            self.org.pk,
            product.pk,
            packaging.pk,
            {"expected_version": 1, "is_active": False},
        )
        with self.assertRaises(catalog.Conflict):
            services.apply(self.owner, self.org.pk, job.pk, {"expected_version": job.version})

    def test_members_cannot_approve_select_create_cancel_or_apply(self):
        job = self.prepared()
        candidate = Candidate.objects.filter(row__job=job).first()
        for operation in [
            lambda: services.review(self.member, self.org.pk, job.pk, candidate.pk, {}),
            lambda: services.apply(self.member, self.org.pk, job.pk, {}),
            lambda: services.cancel(self.member, self.org.pk, job.pk, {}),
            lambda: services.approve_creation(
                self.member, self.org.pk, job.pk, job.rows.get().pk, {}
            ),
        ]:
            with self.assertRaises(PermissionDenied):
                operation()
        self.assertEqual(services.job_in(self.member, self.org.pk, job.pk), job)

    def test_all_job_file_candidate_report_and_mutation_routes_deny_other_tenant(self):
        job = self.prepared()
        candidate = Candidate.objects.filter(row__job=job).first()
        self.client.force_authenticate(self.other)
        for suffix in ["", "file/", "rows/", "candidates/", "errors/", "history/"]:
            self.assertEqual(self.client.get(self.base + f"{job.pk}/" + suffix).status_code, 404)
        for suffix in [
            "validate/",
            "mapping/",
            "process/",
            "apply/",
            "cancel/",
            "refresh/",
            f"candidates/{candidate.pk}/review/",
            f"rows/{job.rows.get().pk}/creation/",
        ]:
            data = {"expected_version": 1}
            if "mapping" in suffix:
                data["mapping"] = {"sku": "sku"}
            elif "review" in suffix:
                data.update(decision="approve", reason="Malicious attempt")
            elif "creation" in suffix:
                data = {"allow_create": True, "reason": "Malicious attempt"}
            self.assertEqual(
                self.client.post(
                    self.base + f"{job.pk}/" + suffix, data, format="json"
                ).status_code,
                404,
                suffix,
            )
        foreign_base = f"/api/v1/organizations/{self.foreign.pk}/imports/"
        self.assertEqual(self.client.get(foreign_base + f"{job.pk}/").status_code, 404)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(self.base + f"{job.pk}/file/").status_code, 200)

    def test_cross_tenant_sku_does_not_reference_foreign_product(self):
        catalog.create_product(
            self.other,
            self.foreign.pk,
            {"sku": "A", "revision": {"name": "Foreign", "change_reason": "Initial"}},
        )
        job = self.prepared()
        self.assertIsNone(job.rows.get().product_id)
        job = self.approve(job)
        services.apply(self.owner, self.org.pk, job.pk, {"expected_version": job.version})
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(AttributeClaim.objects.get().product.organization_id, self.org.pk)

    def test_revoked_suspended_and_crafted_inputs_cannot_bypass_lifecycle(self):
        job = self.prepared()
        self.assertFalse(
            MappingInput(
                data={"expected_version": 1, "mapping": {"sku": "sku", "product_id": "name"}}
            ).is_valid()
        )
        self.assertFalse(
            DecisionInput(
                data={
                    "expected_version": 1,
                    "decision": "approve",
                    "reason": "Test valid",
                    "basis": "measured",
                }
            ).is_valid()
        )
        Membership.objects.filter(user=self.member, organization=self.org).delete()
        with self.assertRaises(NotFound):
            services.job_in(self.member, self.org.pk, job.pk)
        self.org.is_active = False
        self.org.save()
        with self.assertRaises(NotFound):
            services.job_in(self.owner, self.org.pk, job.pk)

    def test_competing_descriptor_approvals_do_not_silently_use_last_row(self):
        job = self.approve(self.prepared(file(b"sku,name\nA,First name\nA,Second name\n")))
        with self.assertRaises(ValidationError):
            services.apply(self.owner, self.org.pk, job.pk, {"expected_version": job.version})
        self.assertFalse(Product.objects.exists())

    def test_selection_occurs_after_all_competing_claims_are_retained(self):
        job = self.approve(
            self.prepared(file(b"sku,name,mass,mass_unit\nA,Box,1.2,kg\nA,Box,1.35,kg\n"))
        )
        chosen = Candidate.objects.filter(row__job=job, field="mass").first()
        services.review(
            self.owner,
            self.org.pk,
            job.pk,
            chosen.pk,
            catalog.validated(
                DecisionInput,
                {
                    "expected_version": chosen.version,
                    "decision": "approve",
                    "reason": "Choose first source after comparison",
                    "select_value": True,
                },
            ),
        )
        job.refresh_from_db()
        services.apply(self.owner, self.org.pk, job.pk, {"expected_version": job.version})
        self.assertEqual(AttributeClaim.objects.count(), 2)
        state = next(
            s
            for s in workflows.attribute_states(Product.objects.get())["results"]
            if s["attribute"] == "mass"
        )
        self.assertEqual(state["status"], "resolved")
        self.assertIsNotNone(state["selected_claim"])
        job.refresh_from_db()
        self.assertEqual(job.counters["unresolved_conflicts"], 0)
        followup = self.approve(self.prepared(file(b"sku,mass,mass_unit\nA,2,kg\n")))
        result = services.apply(
            self.owner, self.org.pk, followup.pk, {"expected_version": followup.version}
        )
        self.assertEqual(result.counters["unresolved_conflicts"], 1)

    def test_invalid_measurement_can_be_rejected_without_losing_valid_rows(self):
        job = self.prepared(file(b"sku,name,mass,mass_unit\nA,Box,=1+1,kg\nB,Other,1.2,kg\n"))
        invalid = Candidate.objects.get(row__job=job, quality="invalid")
        services.review(
            self.owner,
            self.org.pk,
            job.pk,
            invalid.pk,
            catalog.validated(
                DecisionInput,
                {
                    "expected_version": 1,
                    "decision": "reject",
                    "reason": "Formula cells are unsupported",
                    "value": "=1+1",
                },
            ),
        )
        for row in job.rows.all():
            services.approve_creation(
                self.owner,
                self.org.pk,
                job.pk,
                row.pk,
                {"allow_create": True, "reason": "Reviewed creation"},
            )
        for candidate in Candidate.objects.filter(row__job=job, decision="pending"):
            services.review(
                self.owner,
                self.org.pk,
                job.pk,
                candidate.pk,
                catalog.validated(
                    DecisionInput,
                    {
                        "expected_version": candidate.version,
                        "decision": "approve",
                        "reason": "Valid literal source",
                    },
                ),
            )
        job.refresh_from_db()
        result = services.apply(self.owner, self.org.pk, job.pk, {"expected_version": job.version})
        self.assertEqual(result.status, "completed_with_errors")
        self.assertEqual(Product.objects.count(), 2)
        self.assertEqual(AttributeClaim.objects.count(), 1)
        self.assertEqual(ReviewRecord.objects.get(candidate=invalid).action, "reject")

    def test_duplicate_rows_remain_visible_without_duplicate_application(self):
        job = self.prepared(file(b"sku,name\nA,Box\nA,Box\n"))
        second = job.rows.last()
        self.assertTrue(second.errors)
        candidate = second.candidates.get()
        with self.assertRaises(ValidationError):
            services.review(
                self.owner,
                self.org.pk,
                job.pk,
                candidate.pk,
                catalog.validated(
                    DecisionInput,
                    {
                        "expected_version": 1,
                        "decision": "approve",
                        "reason": "Cannot approve duplicate row",
                    },
                ),
            )
        services.review(
            self.owner,
            self.org.pk,
            job.pk,
            candidate.pk,
            catalog.validated(
                DecisionInput,
                {"expected_version": 1, "decision": "reject", "reason": "Duplicate source row"},
            ),
        )
        self.assertEqual(job.rows.count(), 2)

    def test_parser_timeout_and_corrupted_storage_have_safe_errors(self):
        import subprocess

        from django.core.files.storage import storages

        job = services.upload(self.owner, self.org.pk, file())
        with patch(
            "ingestion.parsers.subprocess.run", side_effect=subprocess.TimeoutExpired("worker", 20)
        ):
            with self.assertRaises(ValidationError) as raised:
                parsers.parse(job, {})
            self.assertNotIn(self.tmp.name, str(raised.exception))
        with storages["ingestion"].open(job.storage_key, "wb") as stream:
            stream.write(b"tampered")
        self.assertEqual(self.client.get(self.base + f"{job.pk}/file/").status_code, 400)


class ConcurrentImportTests(ImportFixture, TransactionTestCase):
    def setUp(self):
        self.setup_fixture()

    def test_concurrent_apply_creates_one_catalog_result(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL row locking required")
        job = self.approve(self.prepared())
        gate = Barrier(2)

        def apply_once():
            close_old_connections()
            try:
                gate.wait(timeout=15)
                return services.apply(
                    self.owner, self.org.pk, job.pk, {"expected_version": job.version}
                ).status
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: apply_once(), range(2)))
        self.assertEqual(results, ["completed", "completed"])
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(Evidence.objects.count(), 1)
