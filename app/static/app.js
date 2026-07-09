const form = document.querySelector("#upload-form");
const preview = document.querySelector("#preview");
const result = document.querySelector("#result");
const errorSummary = document.querySelector("#error-summary");
const previewRows = document.querySelector("#preview-rows");
const confirmButton = document.querySelector("#confirm-button");
const backButton = document.querySelector("#back-button");
const downloadLink = document.querySelector("#download-link");
const clearAllButton = document.querySelector("#clear-all");

let activeJobId = null;

function uploadCards() {
  return [...document.querySelectorAll(".upload-card")];
}

function fileInput(card) {
  return card.querySelector('input[type="file"]');
}

function fileList(card) {
  return card.querySelector(".file-list");
}

function listFiles(card) {
  const input = fileInput(card);
  const list = fileList(card);
  list.replaceChildren();

  [...input.files].forEach((file, index) => {
    const item = document.createElement("li");
    item.append(document.createTextNode(file.name));
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "remove-file ghost";
    remove.textContent = "删除";
    remove.addEventListener("click", () => removeFile(input, index));
    item.append(remove);
    list.append(item);
  });
}

async function invalidatePreview() {
  if (!activeJobId) {
    return;
  }
  await fetch(`/api/jobs/${activeJobId}`, { method: "DELETE" });
  activeJobId = null;
  preview.hidden = true;
  previewRows.replaceChildren();
}

async function removeFile(input, removedIndex) {
  const transfer = new DataTransfer();
  [...input.files].forEach((file, index) => {
    if (index !== removedIndex) {
      transfer.items.add(file);
    }
  });
  input.files = transfer.files;
  listFiles(input.closest(".upload-card"));
  await invalidatePreview();
}

function clearErrors() {
  errorSummary.hidden = true;
  errorSummary.replaceChildren();
}

function formatIssue(issue) {
  const parts = [issue.message];
  if (issue.filename) {
    parts.push(`文件：${issue.filename}`);
  }
  if (issue.page !== undefined && issue.page !== null) {
    parts.push(`页码：${issue.page}`);
  }
  if (issue.expected !== undefined || issue.actual !== undefined) {
    parts.push(`期望：${JSON.stringify(issue.expected ?? "-")}`);
    parts.push(`实际：${JSON.stringify(issue.actual ?? "-")}`);
  }
  parts.push(issue.repair);
  return parts.join("；");
}

function showIssues(issues) {
  clearErrors();
  errorSummary.hidden = false;
  errorSummary.textContent = "校验未通过，请按下面的问题修正后重新上传。";
  issues.forEach((issue) => {
    const line = document.createElement("p");
    line.textContent = formatIssue(issue);
    errorSummary.append(line);
  });
}

function resetInputs() {
  uploadCards().forEach((card) => {
    fileInput(card).value = "";
    listFiles(card);
  });
  form.reset();
}

function resetAfterSuccess() {
  resetInputs();
  activeJobId = null;
  preview.hidden = true;
  previewRows.replaceChildren();
  clearErrors();
}

uploadCards().forEach((card) => {
  const input = fileInput(card);
  input.addEventListener("change", async () => {
    listFiles(card);
    await invalidatePreview();
  });
  card.querySelector(".clear-file").addEventListener("click", async () => {
    input.value = "";
    listFiles(card);
    await invalidatePreview();
  });
});

clearAllButton.addEventListener("click", async () => {
  await invalidatePreview();
  resetInputs();
  preview.hidden = true;
  result.hidden = true;
  clearErrors();
});

backButton.addEventListener("click", () => {
  preview.hidden = true;
  result.hidden = true;
  form.hidden = false;
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  await invalidatePreview();
  clearErrors();

  const response = await fetch("/api/jobs/validate", {
    method: "POST",
    body: new FormData(form),
  });
  const body = await response.json();

  if (!response.ok) {
    showIssues(body.detail?.issues ?? []);
    return;
  }

  activeJobId = body.job_id;
  previewRows.replaceChildren(
    ...body.preview.assignments.map((assignment) => {
      const row = document.createElement("tr");
      [
        assignment.shipment_id,
        assignment.carrier_number,
        assignment.shipment_pdf,
        assignment.shipment_txt,
        assignment.carrier_pdf,
        assignment.source_rows.join(", "),
      ].forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      });
      return row;
    }),
  );

  form.hidden = true;
  result.hidden = true;
  preview.hidden = false;
});

confirmButton.addEventListener("click", async () => {
  const response = await fetch(`/api/jobs/${activeJobId}/generate`, {
    method: "POST",
  });
  const body = await response.json();

  if (!response.ok) {
    showIssues(body.detail?.issues ?? []);
    form.hidden = false;
    preview.hidden = true;
    return;
  }

  resetAfterSuccess();
  form.hidden = false;
  result.hidden = false;
  downloadLink.href = body.download_url;
});
