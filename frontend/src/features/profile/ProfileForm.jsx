import { useState } from "react";
import Button from "../../components/Button";
import ErrorBanner from "../../components/ErrorBanner";
import { fieldErrorsFrom } from "../../utils/fieldErrors";
import ProfileFields from "./ProfileFields";
import { useProfileFields } from "./useProfileFields";

export default function ProfileForm({ profile, counties, onSave }) {
  const fields = useProfileFields(profile, counties);
  const [errors, setErrors] = useState({});
  const [status, setStatus] = useState("idle");
  const [formError, setFormError] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    setFormError("");
    const found = fields.validate();
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setStatus("saving");
    try {
      await onSave(fields.payload);
      setStatus("saved");
    } catch (err) {
      const serverErrors = fieldErrorsFrom(err);
      if (Object.keys(serverErrors).length > 0) setErrors(serverErrors);
      else setFormError(err.message);
      setStatus("idle");
    }
  }

  return (
    <form className="profile-form" onSubmit={handleSubmit} noValidate>
      <ProfileFields fields={fields} errors={errors} />
      <ErrorBanner>{formError}</ErrorBanner>
      <Button type="submit" busy={status === "saving"}>
        Save profile
      </Button>
      {status === "saved" && (
        <p className="profile-saved" role="status">
          Saved. Plan questions now use this profile.
        </p>
      )}
    </form>
  );
}
