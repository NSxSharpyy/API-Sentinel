import IncidentAlertCard from "./IncidentAlertCard";

export default function IncidentAlertGrid({ incidents = [] }) {
  if (!Array.isArray(incidents)) {
    return (
      <p role="alert" className="text-sm text-red-700">
        Unable to display incidents: invalid data format.
      </p>
    );
  }

  if (incidents.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-gray-300 bg-white p-8 text-center">
        <p className="font-medium text-gray-800">
          No backend incidents to display
        </p>

        <p className="mt-1 text-sm text-gray-500">
          Persisted alerts will appear here when available.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3">
      {incidents.map((incident, index) => (
        <IncidentAlertCard
          key={incident?.incident_id ?? incident?.id ?? index}
          incident={incident}
        />
      ))}
    </div>
  );
}
