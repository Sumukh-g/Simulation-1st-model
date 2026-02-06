"""Tests for Evidence Service."""
from datetime import datetime, timedelta, timezone

import pytest

from services.evidence import (
    chunk_text,
    ChunkReference,
    EvidencePack,
    EvidencePackBuilder,
    EvidencePackStore,
    Claim,
    ClaimConflict,
    ClaimType,
    ConflictType,
    ClaimDB,
    ClaimExtractor,
    ClaimVerifier,
    UnitNormalizer,
)


class TestChunking:
    """Tests for text chunking."""

    def test_sliding_window_chunking(self):
        """Test sliding window chunking."""
        text = "A" * 1000
        chunks = chunk_text(text, chunk_size=200, overlap=20, method="sliding_window")

        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk["content"]) <= 200
            assert chunk["method"] == "sliding_window"

    def test_paragraph_chunking(self):
        """Test paragraph-based chunking."""
        text = "Paragraph 1.\n\nParagraph 2.\n\nParagraph 3."
        chunks = chunk_text(text, chunk_size=100, method="paragraph")

        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk["method"] == "paragraph"

    def test_sentence_chunking(self):
        """Test sentence-based chunking."""
        text = "Sentence one. Sentence two. Sentence three."
        chunks = chunk_text(text, chunk_size=50, method="sentence")

        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk["method"] == "sentence"


class TestEvidencePack:
    """Tests for EvidencePack."""

    def test_create_pack(self):
        """Test creating an evidence pack."""
        builder = EvidencePackBuilder(run_id="run-001", query="test query")
        builder.add_chunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            source="test.pdf",
            content="Test content",
            score=0.95,
        )

        pack = builder.build()

        assert pack.run_id == "run-001"
        assert pack.query == "test query"
        assert pack.total_chunks == 1
        assert pack.hash != ""

    def test_pack_immutability(self):
        """Test that pack hash changes if content would change."""
        builder = EvidencePackBuilder(run_id="run-001", query="test")
        builder.add_chunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            source="test.pdf",
            content="Content A",
            score=0.9,
        )
        pack1 = builder.build()

        builder2 = EvidencePackBuilder(run_id="run-001", query="test")
        builder2.add_chunk(
            chunk_id="chunk-2",
            document_id="doc-1",
            source="test.pdf",
            content="Content B",
            score=0.9,
        )
        pack2 = builder2.build()

        assert pack1.hash != pack2.hash

    def test_pack_verify_integrity(self):
        """Test pack integrity verification."""
        builder = EvidencePackBuilder(run_id="run-001", query="test")
        builder.add_chunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            source="test.pdf",
            content="Test content",
            score=0.9,
        )
        pack = builder.build()

        assert pack.verify_integrity()

    def test_pack_citations(self):
        """Test generating citation list."""
        builder = EvidencePackBuilder(run_id="run-001", query="test")
        builder.add_chunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            source="report.pdf",
            content="This is the evidence text",
            score=0.92,
        )
        pack = builder.build()

        citations = pack.to_citation_list()
        assert len(citations) == 1
        assert citations[0]["source"] == "report.pdf"
        assert citations[0]["relevance_score"] == 0.92

    def test_pack_store(self):
        """Test storing and retrieving packs."""
        store = EvidencePackStore()

        builder = EvidencePackBuilder(run_id="run-001", query="test")
        builder.add_chunk(
            chunk_id="chunk-1",
            document_id="doc-1",
            source="test.pdf",
            content="Content",
            score=0.9,
        )
        pack = builder.build()

        pack_id = store.store(pack)
        retrieved = store.get(pack_id)

        assert retrieved is not None
        assert retrieved.id == pack.id
        assert retrieved.hash == pack.hash


class TestUnitNormalizer:
    """Tests for unit normalization."""

    def test_length_normalization(self):
        """Test length unit normalization."""
        value, unit = UnitNormalizer.normalize(1.0, "km")
        assert unit == "m"
        assert value == 1000.0

        value, unit = UnitNormalizer.normalize(100.0, "cm")
        assert unit == "m"
        assert value == 1.0

    def test_mass_normalization(self):
        """Test mass unit normalization."""
        value, unit = UnitNormalizer.normalize(1000.0, "g")
        assert unit == "kg"
        assert value == 1.0

    def test_time_normalization(self):
        """Test time unit normalization."""
        value, unit = UnitNormalizer.normalize(1.0, "hours")
        assert unit == "s"
        assert value == 3600.0

    def test_comparable_units(self):
        """Test unit comparability check."""
        assert UnitNormalizer.are_comparable("km", "m")
        assert UnitNormalizer.are_comparable("kg", "g")
        assert not UnitNormalizer.are_comparable("km", "kg")

    def test_unknown_unit(self):
        """Test handling of unknown units."""
        value, unit = UnitNormalizer.normalize(5.0, "widgets")
        assert value == 5.0
        assert unit == "widgets"


class TestClaimExtractor:
    """Tests for claim extraction."""

    def test_extract_numeric_claim(self):
        """Test extracting numeric claims."""
        extractor = ClaimExtractor()
        claims = extractor.extract_from_text(
            text="The revenue is 5000000 USD",
            source_document_id="doc-1",
            source_chunk_id="chunk-1",
            source_name="report.pdf",
        )

        assert len(claims) >= 1
        # At least one claim should be numeric
        numeric_claims = [c for c in claims if c.claim_type == ClaimType.NUMERIC]
        assert len(numeric_claims) >= 1

    def test_create_manual_claim(self):
        """Test creating a claim manually."""
        extractor = ClaimExtractor()
        claim = extractor.create_claim(
            subject="ROI",
            predicate="equals",
            obj="15%",
            claim_type=ClaimType.NUMERIC,
            source_document_id="doc-1",
            source_chunk_id="chunk-1",
            source_text="The ROI is 15%",
            source_name="report.pdf",
            numeric_value=15.0,
            unit="%",
        )

        assert claim.subject == "ROI"
        assert claim.numeric_value == 15.0
        assert claim.unit == "%"


class TestClaimVerifier:
    """Tests for claim verification."""

    def test_detect_numeric_discrepancy(self):
        """Test detecting numeric discrepancies."""
        verifier = ClaimVerifier(numeric_tolerance=0.1)
        extractor = ClaimExtractor()

        claim_a = extractor.create_claim(
            subject="revenue",
            predicate="has_value",
            obj="100 USD",
            claim_type=ClaimType.NUMERIC,
            source_document_id="doc-1",
            source_chunk_id="chunk-1",
            source_text="Revenue is 100 USD",
            source_name="source-a.pdf",
            numeric_value=100.0,
            unit="USD",
        )

        claim_b = extractor.create_claim(
            subject="revenue",
            predicate="has_value",
            obj="150 USD",
            claim_type=ClaimType.NUMERIC,
            source_document_id="doc-2",
            source_chunk_id="chunk-1",
            source_text="Revenue is 150 USD",
            source_name="source-b.pdf",
            numeric_value=150.0,
            unit="USD",
        )

        claims, conflicts = verifier.verify_claims([claim_a, claim_b])

        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.NUMERIC_DISCREPANCY

    def test_no_conflict_within_tolerance(self):
        """Test no conflict when within tolerance."""
        verifier = ClaimVerifier(numeric_tolerance=0.1)
        extractor = ClaimExtractor()

        claim_a = extractor.create_claim(
            subject="revenue",
            predicate="has_value",
            obj="100 USD",
            claim_type=ClaimType.NUMERIC,
            source_document_id="doc-1",
            source_chunk_id="chunk-1",
            source_text="Revenue is 100 USD",
            source_name="source-a.pdf",
            numeric_value=100.0,
            unit="USD",
        )

        claim_b = extractor.create_claim(
            subject="revenue",
            predicate="has_value",
            obj="105 USD",
            claim_type=ClaimType.NUMERIC,
            source_document_id="doc-2",
            source_chunk_id="chunk-1",
            source_text="Revenue is 105 USD",
            source_name="source-b.pdf",
            numeric_value=105.0,
            unit="USD",
        )

        claims, conflicts = verifier.verify_claims([claim_a, claim_b])

        assert len(conflicts) == 0

    def test_unit_mismatch_detection(self):
        """Test detecting unit mismatches."""
        verifier = ClaimVerifier()
        extractor = ClaimExtractor()

        claim_a = extractor.create_claim(
            subject="distance",
            predicate="has_value",
            obj="100 km",
            claim_type=ClaimType.NUMERIC,
            source_document_id="doc-1",
            source_chunk_id="chunk-1",
            source_text="Distance is 100 km",
            source_name="source-a.pdf",
            numeric_value=100.0,
            unit="km",
        )

        claim_b = extractor.create_claim(
            subject="distance",
            predicate="has_value",
            obj="100 kg",  # Wrong unit type
            claim_type=ClaimType.NUMERIC,
            source_document_id="doc-2",
            source_chunk_id="chunk-1",
            source_text="Distance is 100 kg",
            source_name="source-b.pdf",
            numeric_value=100.0,
            unit="kg",
        )

        claims, conflicts = verifier.verify_claims([claim_a, claim_b])

        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == ConflictType.UNIT_MISMATCH

    def test_freshness_conflict_detection(self):
        """Test detecting freshness conflicts."""
        verifier = ClaimVerifier(recency_threshold_days=365)
        extractor = ClaimExtractor()

        old_date = datetime.now(timezone.utc) - timedelta(days=400)
        new_date = datetime.now(timezone.utc)

        claim_a = extractor.create_claim(
            subject="price",
            predicate="has_value",
            obj="50 USD",
            claim_type=ClaimType.NUMERIC,
            source_document_id="doc-1",
            source_chunk_id="chunk-1",
            source_text="Price is 50 USD",
            source_name="old-report.pdf",
            numeric_value=50.0,
            unit="USD",
            claim_date=old_date,
        )

        claim_b = extractor.create_claim(
            subject="price",
            predicate="has_value",
            obj="75 USD",
            claim_type=ClaimType.NUMERIC,
            source_document_id="doc-2",
            source_chunk_id="chunk-1",
            source_text="Price is 75 USD",
            source_name="new-report.pdf",
            numeric_value=75.0,
            unit="USD",
            claim_date=new_date,
        )

        claims, conflicts = verifier.verify_claims([claim_a, claim_b])

        # Should detect freshness conflict
        freshness_conflicts = [
            c for c in conflicts if c.conflict_type == ConflictType.FRESHNESS_CONFLICT
        ]
        assert len(freshness_conflicts) >= 1

    def test_cross_source_consistency(self):
        """Test cross-source consistency scoring."""
        verifier = ClaimVerifier()
        extractor = ClaimExtractor()

        # Create agreeing claims from different sources
        claims = []
        for i, source in enumerate(["source-a.pdf", "source-b.pdf", "source-c.pdf"]):
            claim = extractor.create_claim(
                subject="rate",
                predicate="equals",
                obj="5%",
                claim_type=ClaimType.NUMERIC,
                source_document_id=f"doc-{i}",
                source_chunk_id=f"chunk-{i}",
                source_text="Rate is 5%",
                source_name=source,
                numeric_value=5.0,
                unit="%",
            )
            claims.append(claim)

        consistency = verifier.cross_source_consistency(claims)

        assert "rate" in consistency
        assert consistency["rate"] == 1.0  # All agree


class TestClaimDB:
    """Tests for ClaimDB."""

    def test_add_and_retrieve_claim(self):
        """Test adding and retrieving claims."""
        db = ClaimDB()

        claim = db.extractor.create_claim(
            subject="ROI",
            predicate="equals",
            obj="10%",
            claim_type=ClaimType.NUMERIC,
            source_document_id="doc-1",
            source_chunk_id="chunk-1",
            source_text="ROI is 10%",
            source_name="report.pdf",
            numeric_value=10.0,
            unit="%",
        )

        claim_id = db.add_claim(claim)
        retrieved = db.get_claim(claim_id)

        assert retrieved is not None
        assert retrieved.subject == "ROI"

    def test_get_claims_by_subject(self):
        """Test getting claims by subject."""
        db = ClaimDB()

        for i in range(3):
            claim = db.extractor.create_claim(
                subject="revenue",
                predicate="equals",
                obj=f"{100+i} USD",
                claim_type=ClaimType.NUMERIC,
                source_document_id=f"doc-{i}",
                source_chunk_id=f"chunk-{i}",
                source_text=f"Revenue is {100+i} USD",
                source_name=f"report-{i}.pdf",
                numeric_value=100.0 + i,
                unit="USD",
            )
            db.add_claim(claim)

        claims = db.get_claims_for_subject("revenue")
        assert len(claims) == 3

    def test_verify_all(self):
        """Test verifying all claims."""
        db = ClaimDB()

        # Add conflicting claims
        db.add_claim(
            db.extractor.create_claim(
                subject="cost",
                predicate="equals",
                obj="100 USD",
                claim_type=ClaimType.NUMERIC,
                source_document_id="doc-1",
                source_chunk_id="chunk-1",
                source_text="Cost is 100 USD",
                source_name="source-a.pdf",
                numeric_value=100.0,
                unit="USD",
            )
        )
        db.add_claim(
            db.extractor.create_claim(
                subject="cost",
                predicate="equals",
                obj="200 USD",
                claim_type=ClaimType.NUMERIC,
                source_document_id="doc-2",
                source_chunk_id="chunk-1",
                source_text="Cost is 200 USD",
                source_name="source-b.pdf",
                numeric_value=200.0,
                unit="USD",
            )
        )

        total_claims, total_conflicts = db.verify_all()

        assert total_claims == 2
        assert total_conflicts >= 1

    def test_cite_claim(self):
        """Test citing a claim."""
        db = ClaimDB()

        claim = db.extractor.create_claim(
            subject="ROI",
            predicate="equals",
            obj="15%",
            claim_type=ClaimType.NUMERIC,
            source_document_id="doc-1",
            source_chunk_id="chunk-1",
            source_text="The ROI is 15%",
            source_name="report.pdf",
            numeric_value=15.0,
            unit="%",
        )
        claim_id = db.add_claim(claim)

        citation = db.cite_claim(claim_id)

        assert citation["claim_id"] == claim_id
        assert "ROI" in citation["statement"]
        assert citation["source"] == "report.pdf"
        assert citation["confidence"] == 1.0

    def test_high_confidence_claims(self):
        """Test getting high confidence claims."""
        db = ClaimDB()

        # Add claim with high confidence
        high_conf = db.extractor.create_claim(
            subject="fact1",
            predicate="equals",
            obj="value",
            claim_type=ClaimType.CATEGORICAL,
            source_document_id="doc-1",
            source_chunk_id="chunk-1",
            source_text="Fact 1",
            source_name="source.pdf",
            confidence=0.95,
        )
        db.add_claim(high_conf)

        # Add claim with low confidence
        low_conf = db.extractor.create_claim(
            subject="fact2",
            predicate="equals",
            obj="value",
            claim_type=ClaimType.CATEGORICAL,
            source_document_id="doc-2",
            source_chunk_id="chunk-1",
            source_text="Fact 2",
            source_name="source.pdf",
            confidence=0.3,
        )
        db.add_claim(low_conf)

        high_conf_claims = db.get_high_confidence_claims(min_confidence=0.8)

        assert len(high_conf_claims) == 1
        assert high_conf_claims[0].subject == "fact1"

    def test_summary(self):
        """Test summary statistics."""
        db = ClaimDB()

        db.add_claim(
            db.extractor.create_claim(
                subject="test",
                predicate="equals",
                obj="value",
                claim_type=ClaimType.CATEGORICAL,
                source_document_id="doc-1",
                source_chunk_id="chunk-1",
                source_text="Test",
                source_name="source.pdf",
            )
        )

        summary = db.summary()

        assert summary["total_claims"] == 1
        assert summary["documents_processed"] == 1
